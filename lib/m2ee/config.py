#
# Copyright (c) 2009-2015, Mendix bv
# All Rights Reserved.
#
# http://www.mendix.com/
#

import yaml
import os
import sys
import pwd
import re
import copy

from .log import logger
from collections import defaultdict
from .version import MXVersion

# Use json if available. If not (python 2.5) we need to import the simplejson
# module instead, which has to be available.
try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError as ie:
        logger.critical("Failed to import json as well as simplejson. If "
                        "using python 2.5, you need to provide the simplejson "
                        "module in your python library path.")
        raise


class M2EEConfig:

    def __init__(self, load_default_files=True, yaml_files=None, config=None):
        _yaml_files = []
        if load_default_files:
            _yaml_files.extend(find_yaml_files())
        if yaml_files:
            _yaml_files.extend(yaml_files)

        self._mtimes, self._conf = read_yaml_files(_yaml_files)

        if config:
            self._conf = merge_config(self._conf, config)

        self._all_systems_are_go = True

        self._check_appcontainer_config()
        self._check_runtime_config()
        self._conf['mxruntime'].setdefault(
            'BasePath', self._conf['m2ee']['app_base'])

        self._conf['mxruntime'].setdefault('DTAPMode', 'P')

        self.fix_permissions()

        self._appcontainer_version = self._conf['m2ee'].get(
            'appcontainer_version', None)

        # >= 3.0: application information (e.g. runtime version)
        # if this file does not exist (i.e. < 3.0) try_load_json returns {}
        self._model_metadata = self._try_load_json(
            os.path.join(
                self._conf['m2ee']['app_base'],
                'model',
                'metadata.json',
            ))

        self.runtime_version = self._lookup_runtime_version()

        self._conf['mxruntime'] = self._merge_microflow_constants()

        self._runtime_path = None
        if (not self._run_from_source or
                self._run_from_source == 'appcontainer'):
            if self.runtime_version is None:
                logger.info("Unable to look up mendix runtime files "
                            "because product version is yet unknown.")
                self._all_systems_are_go = False
            else:
                self._runtime_path = self.lookup_in_mxjar_repo(
                    str(self.runtime_version))
                if self._runtime_path is None:
                    self._all_systems_are_go = False

        self._setup_classpath()

        if self._runtime_path and 'RuntimePath' not in self._conf['mxruntime']:
            runtimePath = os.path.join(self._runtime_path, 'runtime')
            logger.debug("Setting RuntimePath runtime config option to %s"
                         % runtimePath)
            self._conf['mxruntime']['RuntimePath'] = runtimePath

    def _setup_classpath(self):
        logger.debug("Determining classpath to be used...")

        classpath = []

        if self._run_from_source:
            logger.debug("Building classpath to run hybrid appcontainer from "
                         "source.")
            classpath = self._setup_classpath_from_source()
        elif self.use_hybrid_appcontainer() and self.runtime_version < 5:
            logger.debug("Hybrid appcontainer from jars does not need a "
                         "classpath.")
            self._appcontainer_jar = self._lookup_appcontainer_jar()
        elif not self._appcontainer_version or self.runtime_version >= 5:
            logger.debug("Building classpath to run appcontainer/runtime from "
                         "jars.")
            classpath = self._setup_classpath_runtime_binary()
            classpath.extend(self._setup_classpath_model())

        if 'extend_classpath' in self._conf['m2ee']:
            if isinstance(self._conf['m2ee']['extend_classpath'], list):
                classpath.extend(self._conf['m2ee']['extend_classpath'])
            else:
                logger.warn("extend_classpath option in m2ee section in "
                            "configuration is not a list")

        self._classpath = ":".join(classpath)
        if self._classpath:
            logger.debug("Using classpath: %s" % self._classpath)
        else:
            logger.debug("No classpath will be used")

    def _merge_microflow_constants(self):
        """
        3.0: config.json "contains the configuration settings of the active
        configuration (in the Modeler) at the time of deployment." It also
        contains default values for microflow constants. D/T configuration is
        not stored in the mdp anymore, so for D/T we need to insert it into
        the configuration we read from yaml (yay!)
        { "Configuration": { "key": "value", ... }, "Constants": {
        "Module.Constant": "value", ... } } also... move the custom section
        into the MicroflowConstants runtime config option where 3.0 now
        expects them to be! yay... (when running 2.5, the MicroflowConstants
        part of runtime config will be sent using the old
        update_custom_configuration m2ee api call. Fun!
        """

        logger.debug("Merging microflow constants configuration...")

        config_json = {}
        if not self.get_dtap_mode()[0] in ('A', 'P'):
            config_json_file = os.path.join(self._conf['m2ee']['app_base'],
                                            'model',
                                            'config.json'
                                            )
            logger.trace("In DTAPMode %s, so loading configuration from %s" %
                         (self.get_dtap_mode(), config_json_file)
                         )
            config_json = self._try_load_json(config_json_file)

        # figure out which constants to use
        merge_constants = {}
        if not self.get_dtap_mode()[0] in ('A', 'P'):
            config_json_constants = config_json.get('Constants', {})
            logger.trace("In DTAPMode %s, so using Constants from "
                         "config.json: %s" %
                         (self.get_dtap_mode(), config_json_constants))
            merge_constants.update(config_json_constants)
        # custom yaml section can override defaults
        yaml_custom = self._conf.get('custom', {})
        if yaml_custom:
            logger.trace("Using constants from custom config section: %s" %
                         yaml_custom)
            merge_constants.update(yaml_custom)
        # 'MicroflowConstants' from runtime yaml section can override
        # default/custom
        yaml_mxruntime_mfconstants = (
            self._conf['mxruntime'].get('MicroflowConstants', {}))
        if yaml_mxruntime_mfconstants:
            logger.trace("Using constants from mxruntime/MicroflowConstants: "
                         "%s" % yaml_mxruntime_mfconstants)
            merge_constants.update(yaml_mxruntime_mfconstants)
        # merge all yaml runtime settings into config
        merge_config = {}
        if not self.get_dtap_mode()[0] in ('A', 'P'):
            config_json_configuration = config_json.get('Configuration', {})
            logger.trace("In DTAPMode %s, so seeding runtime configuration "
                         "with Configuration from config.json: %s" %
                         (self.get_dtap_mode(), config_json_configuration))
            merge_config.update(config_json_configuration)
        merge_config.update(self._conf['mxruntime'])
        logger.trace("Merging current mxruntime config into it... %s" %
                     self._conf['mxruntime'])
        # replace 'MicroflowConstants' with mfconstants we just figured out
        # before to prevent dict-deepmerge-problems
        merge_config['MicroflowConstants'] = merge_constants
        logger.trace("Replacing 'MicroflowConstants' with constants we just "
                     "figured out: %s" % merge_constants)
        # the merged result will be put back into self._conf['mxruntime']
        logger.debug("Merged runtime configuration: %s" % merge_config)
        return merge_config

    def _try_load_json(self, jsonfile):
        logger.debug("Loading json configuration from %s" % jsonfile)
        fd = None
        try:
            fd = open(jsonfile)
        except Exception as e:
            logger.debug("Error reading configuration file %s: %s; "
                         "ignoring..." % (jsonfile, e))
            return {}

        config = None
        try:
            config = json.load(fd)
        except Exception as e:
            logger.error("Error parsing configuration file %s: %s" %
                         (jsonfile, e))
            return {}

        logger.trace("contents read from %s: %s" % (jsonfile, config))
        return config

    def mtime_changed(self):
        for yamlfile, mtime in self._mtimes.items():
            if os.stat(yamlfile)[8] != mtime:
                return True
        return False

    def dump(self):
        print(yaml.dump(self._conf))

    def _check_appcontainer_config(self):
        # did we load any configuration at all?
        if not self._conf:
            logger.critical("No configuration present. Please put a m2ee.yaml "
                            "configuration file at the default location "
                            "~/.m2ee/m2ee.yaml or specify an alternate "
                            "configuration file using the -c option.")
            sys.exit(1)

        # TODO: better exceptions
        self._run_from_source = self._conf.get(
            'mxnode', {}).get('run_from_source', False)

        # mxnode
        if self._run_from_source:
            if not self._conf['mxnode'].get('source_workspace', None):
                logger.critical("Run from source was selected, but "
                                "source_workspace is not specified!")
                sys.exit(1)
            if not self._conf['mxnode'].get('source_projects', None):
                logger.critical("Run from source was selected, but "
                                "source_projects is not specified!")
                sys.exit(1)

        # m2ee
        for option in ['app_base', 'admin_port', 'admin_pass']:
            if not self._conf['m2ee'].get(option, None):
                logger.critical("Option %s in configuration section m2ee is "
                                "not defined!" % option)
                sys.exit(1)

        # force admin_pass to a string, prevent TypeError when base64-ing it
        # before sending to m2ee api
        self._conf['m2ee']['admin_pass'] = str(
            self._conf['m2ee']['admin_pass'])

        # Mendix >= 4.3: admin and runtime port only bind to localhost by
        # default
        self._conf['m2ee']['admin_listen_addresses'] = (
            self._conf['m2ee'].get('admin_listen_addresses', ""))
        self._conf['m2ee']['runtime_listen_addresses'] = (
            self._conf['m2ee'].get('runtime_listen_addresses', ""))

        # check admin_pass 1 or password... refuse to accept when users don't
        # change default passwords
        if (self._conf['m2ee']['admin_pass'] == '1' or
                self._conf['m2ee']['admin_pass'] == 'password'):
            logger.critical("Using admin_pass '1' or 'password' is not "
                            "allowed. Please put a long, random password into "
                            "the admin_pass configuration option. At least "
                            "change the default!")
            sys.exit(1)

        # database_dump_path
        if 'database_dump_path' not in self._conf['m2ee']:
            self._conf['m2ee']['database_dump_path'] = os.path.join(
                self._conf['m2ee']['app_base'], 'data', 'database')
        if not os.path.isdir(self._conf['m2ee']['database_dump_path']):
            logger.warn("Database dump path %s is not a directory" %
                        self._conf['m2ee']['database_dump_path'])

    def _check_runtime_config(self):
        self._run_from_source = self._conf.get(
            'mxnode', {}).get('run_from_source', False)

        if (not self._run_from_source or
                self._run_from_source == 'appcontainer'):
            # ensure mxjar_repo is a list, multiple locations are allowed for
            # searching
            if not self._conf.get('mxnode', {}).get('mxjar_repo', None):
                self._conf['mxnode']['mxjar_repo'] = []
            elif not type(self._conf.get('mxnode', {})['mxjar_repo']) == list:
                self._conf['mxnode']['mxjar_repo'] = [
                    self._conf['mxnode']['mxjar_repo']]
        # m2ee
        for option in ['app_name', 'app_base', 'runtime_port']:
            if not self._conf['m2ee'].get(option, None):
                logger.warn("Option %s in configuration section m2ee is not "
                            "defined!" % option)
        # check some locations for existance and permissions
        basepath = self._conf['m2ee']['app_base']
        if not os.path.exists(basepath):
            logger.critical("Application base directory %s does not exist!" %
                            basepath)
            sys.exit(1)

        # model_upload_path
        if 'model_upload_path' not in self._conf['m2ee']:
            self._conf['m2ee']['model_upload_path'] = os.path.join(
                self._conf['m2ee']['app_base'], 'data', 'model-upload')
        if not os.path.isdir(self._conf['m2ee']['model_upload_path']):
            logger.warn("Model upload path %s is not a directory" %
                        self._conf['m2ee']['model_upload_path'])

        # magically add app_base/runtimes to mxjar_repo when it's present
        magic_runtimes = os.path.join(self._conf['m2ee']['app_base'],
                                      'runtimes')
        if ((magic_runtimes not in self._conf['mxnode']['mxjar_repo']
             and os.path.isdir(magic_runtimes))):
            self._conf['mxnode']['mxjar_repo'].insert(0, magic_runtimes)

    def fix_permissions(self):
        basepath = self._conf['m2ee']['app_base']
        for directory, mode in {
                "model": 0o0700,
                "web": 0o0755,
                "data": 0o0700}.items():
            fullpath = os.path.join(basepath, directory)
            if not os.path.isdir(fullpath):
                logger.warn("Directory '%s' does not exist, unable to fixup permissions!" %
                            fullpath)
                continue
            try:
                if os.stat(fullpath).st_mode & 0xFFF != mode:
                    os.chmod(fullpath, mode)
                    logger.info("Fixing up permissions of directory '%s' "
                                "with mode %s" % (directory, oct(mode)[-3:]))
            except Exception as e:
                logger.error("Unable to fixup permissions of directory '%s' "
                             "with mode %s: %s, Ignoring." % (directory, oct(mode)[-3:], e))

    def get_felix_config_file(self):
        return self._conf['m2ee'].get(
            'felix_config_file',
            os.path.join(
                self._conf['m2ee']['app_base'],
                'model',
                'felixconfig.properties'
            )
        )

    def write_felix_config(self):
        felix_config_file = self.get_felix_config_file()
        felix_config_path = os.path.dirname(felix_config_file)
        if not os.access(felix_config_path, os.W_OK):
            logger.critical("felix_config_file is not in a writable "
                            "location: %s" % felix_config_path)
            return False

        project_bundles_path = os.path.join(
            self._conf['m2ee']['app_base'], 'model', 'bundles'
        )
        osgi_storage_path = os.path.join(
            self._conf['m2ee']['app_base'], 'data', 'tmp', 'felixcache'
        )
        felix_template_file = os.path.join(
            self._runtime_path,
            'runtime',
            'felixconfig.properties.template'
        )
        if os.path.exists(felix_template_file):
            logger.debug("writing felix configuration template from %s "
                         "to %s" % (felix_template_file, felix_config_file))
            try:
                input_file = open(felix_template_file)
                template = input_file.read()
            except IOError as e:
                logger.error("felix configuration template could not be "
                             "read: %s", e)
                return False
            try:
                output_file = open(felix_config_file, 'w')
                render = template.format(
                    ProjectBundlesDir=project_bundles_path,
                    InstallDir=self._runtime_path,
                    FrameworkStorage=osgi_storage_path
                )
                output_file.write(render)
            except IOError as e:
                logger.error("felix configuration file could not be "
                             "written: %s", e)
                return False
        else:
            logger.error("felix configuration template is not a readable "
                         "file: %s" % felix_template_file)
            return False
        return True

    def get_app_name(self):
        return self._conf['m2ee']['app_name']

    def get_app_base(self):
        return self._conf['m2ee']['app_base']

    def get_default_dotm2ee_directory(self):
        dotm2ee = os.path.join(pwd.getpwuid(os.getuid())[5], ".m2ee")
        if not os.path.isdir(dotm2ee):
            try:
                os.mkdir(dotm2ee)
            except OSError as e:
                logger.debug("Got %s: %s" % (type(e), e))
                import traceback
                logger.debug(traceback.format_exc())
                logger.critical("Directory %s does not exist, and cannot be "
                                "created!")
                logger.critical("If you do not want to use .m2ee in your home "
                                "directory, you have to specify pidfile, "
                                "munin -> config_cache in your configuration "
                                "file")
                sys.exit(1)

        return dotm2ee

    def get_runtime_blocking_connector(self):
        return self._conf['m2ee'].get('runtime_blocking_connector', False)

    def get_symlink_mxclientsystem(self):
        return self._conf['m2ee'].get('symlink_mxclientsystem', True)

    def get_post_unpack_hook(self):
        return self._conf['m2ee'].get('post_unpack_hook', False)

    def get_public_webroot_path(self):
        return self._conf['mxruntime'].get('PublicWebrootPath',
                                           os.path.join(
                                               self._conf['m2ee']['app_base'],
                                               'web'))

    def get_real_mxclientsystem_path(self):
        if 'MxClientSystemPath' in self._conf['mxruntime']:
            return self._conf['mxruntime'].get('MxClientSystemPath')
        else:
            return os.path.join(
                self._runtime_path,
                'runtime',
                'mxclientsystem')

    def get_mimetypes(self):
        return self._conf['mimetypes']

    def all_systems_are_go(self):
        return self._all_systems_are_go

    def get_java_env(self):
        env = {}

        preserve_environment = self._conf['m2ee'].get('preserve_environment',
                                                      False)
        if preserve_environment is True:
            env = os.environ.copy()
        elif preserve_environment is False:
            pass
        elif type(preserve_environment) == list:
            for varname in preserve_environment:
                if varname in os.environ:
                    env[varname] = os.environ[varname]
                else:
                    logger.warn("preserve_environment variable %s is not "
                                "present in os.environ" % varname)
        else:
            logger.warn("preserve_environment is not a boolean or list")

        custom_environment = self._conf['m2ee'].get('custom_environment', {})
        if custom_environment is not None:
            if type(custom_environment) == dict:
                env.update(custom_environment)
            else:
                logger.warn("custom_environment option in m2ee section in "
                            "configuration is not a dictionary")

        env.update({
            'M2EE_ADMIN_PORT': str(self._conf['m2ee']['admin_port']),
            'M2EE_ADMIN_PASS': str(self._conf['m2ee']['admin_pass']),
            # only has effect with Mendix >= 4.3, but include anyway as
            # it does not break earlier versions
            'M2EE_ADMIN_LISTEN_ADDRESSES': str(
                self._conf['m2ee']['admin_listen_addresses']),
            'M2EE_RUNTIME_LISTEN_ADDRESSES': str(
                self._conf['m2ee']['runtime_listen_addresses']),
        })

        # only add RUNTIME environment variables when using default
        # appcontainer from runtime distro
        if not self._appcontainer_version and self.runtime_version < 5:
            env['M2EE_RUNTIME_PORT'] = str(self._conf['m2ee']['runtime_port'])
            if 'runtime_blocking_connector' in self._conf['m2ee']:
                env['M2EE_RUNTIME_BLOCKING_CONNECTOR'] = str(
                    self._conf['m2ee']['runtime_blocking_connector'])

        if 'monitoring_pass' in self._conf['m2ee']:
            env['M2EE_MONITORING_PASS'] = str(
                self._conf['m2ee']['monitoring_pass'])

        return env

    def get_java_cmd(self):
        """
        Build complete JVM startup command line
        """
        cmd = []
        cmd.append(self._conf['m2ee'].get('javabin', 'java'))

        if 'javaopts' in self._conf['m2ee']:
            if isinstance(self._conf['m2ee']['javaopts'], list):
                cmd.extend(self._conf['m2ee']['javaopts'])
            else:
                logger.warn("javaopts option in m2ee section in configuration "
                            "is not a list")
        if self.runtime_version >= 7:
            cmd.extend([
                '-DMX_INSTALL_PATH=%s' % self._runtime_path,
                '-jar',
                os.path.join(
                    self._runtime_path,
                    'runtime/launcher/runtimelauncher.jar'
                ),
                self.get_app_base(),
            ])
        elif self._classpath:
            cmd.extend(['-cp', self._classpath])

            if self.runtime_version >= 5:
                cmd.append('-Dfelix.config.properties=file:%s'
                           % self.get_felix_config_file())

            cmd.append(self._get_appcontainer_mainclass())
        elif self._appcontainer_version:
            cmd.extend(['-jar', self._appcontainer_jar])
        else:
            logger.critical("Unable to determine JVM startup parameters.")
            return None

        return cmd

    def _lookup_appcontainer_jar(self):
        if self._appcontainer_version is None:
            # this probably means a bug in this program
            logger.critical("Trying to look up appcontainer jar, but "
                            "_appcontainer_version is not defined.")
            self._all_systems_are_go = False
            return ""

        appcontainer_path = self.lookup_in_mxjar_repo(
            'appcontainer-%s' % self._appcontainer_version)
        if appcontainer_path is None:
            logger.critical("AppContainer not found for version %s" %
                            self._appcontainer_version)
            self._all_systems_are_go = False
            return ""

        return os.path.join(appcontainer_path, 'appcontainer.jar')

    def get_admin_port(self):
        return self._conf['m2ee']['admin_port']

    def get_admin_pass(self):
        return self._conf['m2ee']['admin_pass']

    def get_xmpp_credentials(self):
        if 'xmpp' in self._conf['m2ee']:
            if isinstance(self._conf['m2ee']['xmpp'], dict):
                return self._conf['m2ee']['xmpp']
            else:
                logger.warn("xmpp option in m2ee section in configuration is "
                            "not a dictionary")
        return None

    def get_runtime_port(self):
        return self._conf['m2ee']['runtime_port']

    def get_runtime_listen_addresses(self):
        return self._conf['m2ee'].get('runtime_listen_addresses', '')

    def get_pidfile(self):
        return self._conf['m2ee'].get('pidfile',
                                      os.path.join(
                                          self.get_default_dotm2ee_directory(),
                                          'm2ee.pid'))

    def get_logfile(self):
        return self._conf['m2ee'].get('logfile', None)

    def get_runtime_config(self):
        return self._conf['mxruntime']

    def get_logging_config(self):
        return self._conf['logging']

    def get_jetty_options(self):
        jetty_opts = copy.deepcopy(self._conf['m2ee'].get('jetty'))
        if jetty_opts is None:
            jetty_opts = {}
        if self.get_runtime_version() >= 5:
            jetty_opts['use_blocking_connector'] = (
                jetty_opts.get('use_blocking_connector',
                               self.get_runtime_blocking_connector()))
        return jetty_opts

    def get_munin_options(self):
        return self._conf['m2ee'].get('munin', {})

    def get_dtap_mode(self):
        return self._conf['mxruntime']['DTAPMode'].upper()

    def allow_destroy_db(self):
        return self._conf['m2ee'].get('allow_destroy_db', True)

    def is_using_postgresql(self):
        databasetype = self._conf['mxruntime'].get('DatabaseType', None)
        return (isinstance(databasetype, str) and
                databasetype.lower() == "postgresql")

    def get_pg_environment(self):
        if not self.is_using_postgresql():
            logger.warn("Only PostgreSQL databases are supported right now.")
        # rip additional :port from hostName, but allow occurrence of plain
        # ipv6 address between []-brackets (simply assume [ipv6::] when ']' is
        # found in string (also see JDBCDataStoreConfiguration in MxRuntime)
        host = self._conf['mxruntime']['DatabaseHost']
        port = "5432"
        ipv6end = host.rfind(']')
        lastcolon = host.rfind(':')
        if ipv6end != -1 and lastcolon > ipv6end:
            # "]" found and ":" exists after the "]"
            port = host[lastcolon + 1:]
            host = host[1:ipv6end]
        elif ipv6end != -1:
            # "]" found but no ":" exists after the "]"
            host = host[1:ipv6end]
        elif ipv6end == -1 and lastcolon != -1:
            # no "]" found and ":" exists, simply split on ":"
            port = host[lastcolon + 1:]
            host = host[:lastcolon]

        # TODO: sanity checks
        pg_env = {
            'PGHOST': host,
            'PGPORT': port,
            'PGUSER': self._conf['mxruntime']['DatabaseUserName'],
            'PGPASSWORD': self._conf['mxruntime']['DatabasePassword'],
            'PGDATABASE': self._conf['mxruntime']['DatabaseName'],
        }
        logger.trace("PostgreSQL environment variables: %s" % str(pg_env))
        return pg_env

    def get_psql_binary(self):
        return self._conf['mxnode'].get('psql', 'psql')

    def get_pg_dump_binary(self):
        return self._conf['mxnode'].get('pg_dump', 'pg_dump')

    def get_pg_restore_binary(self):
        return self._conf['mxnode'].get('pg_restore', 'pg_restore')

    def get_first_writable_mxjar_repo(self):
        repos = self._conf['mxnode']['mxjar_repo']
        logger.debug("Searching for writeable mxjar repos... in %s"
                     % repos)
        repos = [repo for repo in repos if os.access(repo, os.W_OK)]
        if len(repos) > 0:
            found = repos[0]
            logger.debug("Found writable mxjar location: %s" % found)
            return found
        else:
            logger.debug("No writable mxjar location found")
            return None

    def get_runtime_download_url(self, version):
        url = self._conf['mxnode'].get(
            'download_runtime_url',
            'https://download.mendix.com/runtimes/'
        )
        if url[-1] != '/':
            url += '/'
        url += 'mendix-%s.tar.gz' % version
        return url

    def get_database_dump_path(self):
        return self._conf['m2ee']['database_dump_path']

    def get_model_upload_path(self):
        return self._conf['m2ee']['model_upload_path']

    def get_appcontainer_version(self):
        return self._appcontainer_version

    def use_hybrid_appcontainer(self):
        return self._appcontainer_version is not None

    def get_runtime_version(self):
        return self.runtime_version

    def get_classpath(self):
        return self._classpath

    def _get_appcontainer_mainclass(self):
        if self.runtime_version // 2.5:
            return "com.mendix.m2ee.server.M2EE"
        if self.runtime_version // 3 or self.runtime_version // 4:
            if self.use_hybrid_appcontainer():
                return "com.mendix.m2ee.AppContainer"
            return "com.mendix.m2ee.server.HttpAdminAppContainer"
        if self.runtime_version >= 5:
            return "org.apache.felix.main.Main"

        raise Exception("Trying to determine appcontainer main class for "
                        "runtime version %s. Please report this as a bug." %
                        self.runtime_version)

    def _setup_classpath_from_source(self):
        # when running from source, grab eclipse projects:
        logger.debug("Running from source.")
        classpath = []

        wsp = self._conf['mxnode']['source_workspace']
        for proj in self._conf['mxnode']['source_projects']:
            classpath.append(os.path.join(wsp, proj, 'bin'))
            libdir = os.path.join(wsp, proj, 'lib')
            if os.path.isdir(libdir):
                classpath.append(os.path.join(libdir, '*'))

        return classpath

    def _setup_classpath_runtime_binary(self):
        """
        Returns the location of the mendix runtime files and the
        java classpath or None if the classpath cannot be determined
        (i.e. the Mendix Runtime is not available on this system)
        """

        logger.debug("Running from binary distribution.")
        classpath = []

        if not self._runtime_path:
            logger.debug("runtime_path is empty, no classpath can be "
                         "determined")
            return []

        if self.runtime_version < 5:
            classpath.extend([
                os.path.join(self._runtime_path, 'server', '*'),
                os.path.join(self._runtime_path, 'server', 'lib', '*'),
                os.path.join(self._runtime_path, 'runtime', '*'),
                os.path.join(self._runtime_path, 'runtime', 'lib', '*'),
            ])
        elif self.runtime_version >= 5:
            classpath.extend([
                os.path.join(self._runtime_path, 'runtime', 'felix', 'bin',
                             'felix.jar'),
                os.path.join(self._runtime_path, 'runtime', 'lib',
                             'com.mendix.xml-apis-1.4.1.jar')
            ])

        return classpath

    def _setup_classpath_model(self):

        classpath = []

        if self.runtime_version < 5:
            # put model lib into classpath
            model_lib = os.path.join(
                self._conf['m2ee']['app_base'],
                'model',
                'lib'
            )
            if os.path.isdir(model_lib):
                # put all jars into classpath
                classpath.append(os.path.join(model_lib, 'userlib', '*'))
                # put all directories as themselves into classpath
                classpath.extend(
                    [os.path.join(model_lib, name)
                        for name in os.listdir(model_lib)
                        if os.path.isdir(os.path.join(model_lib, name))
                     ])
            else:
                logger.info("No current unpacked application model is available. "
                            "Use the unpack command to unpack a mendix deployment "
                            "archive from %s" % self._conf['m2ee']['model_upload_path'])

        return classpath

    def _lookup_runtime_version(self):
        logger.debug("Determining runtime version to be used...")

        # force to a specific version
        if self._conf['m2ee'].get('runtime_version', None):
            logger.debug("Runtime version forced to %s in configuration" %
                         self._conf['m2ee']['runtime_version'])
            return MXVersion(self._conf['m2ee']['runtime_version'])

        # 3.0 has runtime version in metadata.json
        if 'RuntimeVersion' in self._model_metadata:
            logger.debug("MxRuntime version listed in model metadata: %s" %
                         self._model_metadata['RuntimeVersion'])
            return MXVersion(self._model_metadata['RuntimeVersion'])

        # else, 2.5: try to read from model.mdp using sqlite
        import sqlite3
        model_mdp = os.path.join(
            self._conf['m2ee']['app_base'],
            'model',
            'model.mdp'
        )
        if not os.path.isfile(model_mdp):
            logger.debug("Mendix 2.5? No, %s is not a file! Giving up now..." %
                         model_mdp)
            return None
        version = None
        try:
            conn = sqlite3.connect(model_mdp)
            c = conn.cursor()
            c.execute('SELECT _ProductVersion FROM _MetaData LIMIT 1;')
            version = c.fetchone()[0]
            c.close()
            conn.close()
        except sqlite3.Error as e:
            logger.error("An error occured while trying to read mendix "
                         "version number from model.mdp: %s" % e)
            return None

        # hack: force convert sqlite string to ascii, this prevents syslog from
        # stumbling over it because a BOM will appear which messes up syslog
        # <U+FEFF><183>m2ee: (bofht) DEBUG - MxRuntime version listed in
        # application model file: 2.5.3 also see
        # http://en.wikipedia.org/wiki/Byte_order_mark
        version = version.encode('ascii', 'ignore')
        # TODO: is this only syslog cosmetics, or does splitting syslog into
        # files based on progname break here? needs a bit of testing...

        if not re.match(r'^[\w.-]+$', version):
            logger.error("Invalid version number in model.mdp: %s (not a "
                         "release build?)" % version)
            return None

        logger.debug("MxRuntime version listed in application model file: %s" %
                     version)

        return MXVersion(version)

    def lookup_in_mxjar_repo(self, dirname):
        logger.debug("Searching for %s in mxjar repo locations..." % dirname)
        path = None
        for repo in self._conf['mxnode']['mxjar_repo']:
            try_path = os.path.join(repo, dirname)
            if os.path.isdir(try_path):
                path = try_path
                logger.debug("Using: %s" % path)
                break

        return path

    def get_runtime_path(self):
        return self._runtime_path

    def has_database_password(self):
        return 'DatabasePassword' in self._conf['mxruntime']

    def _warn_constants(self):
        if 'Constants' not in self._model_metadata:
            return
        if 'MicroflowConstants' not in self._conf['mxruntime']:
            return

        model_constants = [
            constant['Name']
            for constant
            in self._model_metadata['Constants']
        ]
        yaml_constants = list(self._conf['mxruntime']['MicroflowConstants'].keys())

        missing = [m for m in model_constants if m not in yaml_constants]
        if missing:
            logger.warn('Constants not defined:')
            for constant in missing:
                logger.warn('- %s' % constant)

        obsolete = [m for m in yaml_constants if m not in model_constants]
        if obsolete:
            logger.info('Constants defined but not needed by application:')
            for constant in obsolete:
                logger.info('- %s' % constant)


def find_yaml_files():
    yaml_files = []
    # don't add deprecated m2eerc-file if yaml is present
    # (if both exist, probably one is a symlink to the other...)
    if os.path.isfile("/etc/m2ee/m2ee.yaml"):
        yaml_files.append("/etc/m2ee/m2ee.yaml")
    elif os.path.isfile("/etc/m2ee/m2eerc"):
        yaml_files.append("/etc/m2ee/m2eerc")

    homedir = pwd.getpwuid(os.getuid())[5]
    if os.path.isfile(os.path.join(homedir, ".m2ee/m2ee.yaml")):
        yaml_files.append(os.path.join(homedir, ".m2ee/m2ee.yaml"))
    elif os.path.isfile(os.path.join(homedir, ".m2eerc")):
        yaml_files.append(os.path.join(homedir, ".m2eerc"))
    return yaml_files


def read_yaml_files(yaml_files):
    config = defaultdict(dict)
    yaml_mtimes = {}

    for yaml_file in yaml_files:
        additional_config = load_config(yaml_file)
        config = merge_config(config, additional_config)
        yaml_mtimes[yaml_file] = os.stat(yaml_file)[8]

    return (yaml_mtimes, config)


def load_config(yaml_file):
    logger.debug("Loading configuration from %s" % yaml_file)
    fd = None
    try:
        fd = open(yaml_file)
    except Exception as e:
        logger.error("Error reading configuration file %s, ignoring..." %
                     yaml_file)
        return

    try:
        return yaml.load(fd, Loader=yaml.FullLoader)
    except Exception as e:
        logger.error("Error parsing configuration file %s: %s" %
                     (yaml_file, e))
        return


def merge_config(initial_config, additional_config):
    result = copy.deepcopy(initial_config)
    if additional_config is None:
        return result
    additional_config = copy.deepcopy(additional_config)
    if initial_config is None:
        return additional_config

    for section in set(list(initial_config.keys()) + list(additional_config.keys())):
        if section in initial_config:
            if section in additional_config:
                if isinstance(additional_config[section], dict):
                    result[section] = merge_config(initial_config[section],
                                                   additional_config[section])
                elif isinstance(additional_config[section], list):
                    result[section] = (initial_config[section] +
                                       additional_config[section])
                else:
                    result[section] = additional_config[section]
        else:
            result[section] = additional_config[section]

    return result


if __name__ == '__main__':
    config = M2EEConfig(sys.argv[1:])
    config.dump()
