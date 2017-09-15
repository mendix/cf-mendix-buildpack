import json
import crypt
import random
import os


def _salt():
    """Returns a string of 2 random letters"""
    letters = 'abcdefghijklmnopqrstuvwxyz' \
              'ABCDEFGHIJKLMNOPQRSTUVWXYZ' \
              '0123456789/.'
    return random.choice(letters) + random.choice(letters)


def gen_htpasswd(users_passwords, file_name_suffix=''):
    with open('nginx/.htpasswd' + file_name_suffix, 'w') as fh:
        for user, password in users_passwords.items():
            if not password:
                fh.write("\n")
            else:
                fh.write(
                    "%s:%s\n" % (
                        user,
                        crypt.crypt(password, _salt())
                    )
                )


def get_path_config():
    '''
    Example for ACCESS_RESTRICTIONS
    {
        "/": {'ipfilter': ['10.0.0.0/8'], 'client_cert': true, 'satisfy': 'any'},
        "/ws/MyWebService/": {'ipfilter': ['10.0.0.0/8'], 'client_cert': true, 'satisfy': 'all'},
        "/CustomRequestHandler/": {'ipfilter': ['10.0.0.0/8']},
        "/CustomRequestHandler2/": {'basic_auth': {'user1': 'password', 'user2': 'password2'}},
    }
    Default for satisfy is all
    '''
    restrictions = json.loads(os.environ.get('ACCESS_RESTRICTIONS', '{}'))
    result = ''
    if '/' not in restrictions:
        restrictions['/'] = {}

    index = 0
    for path, config in restrictions.iteritems():
        if path in ['/_mxadmin/', '/client-cert-check-internal']:
            raise Exception(
                'Can not override access restrictions on system path %s' % path
            )
        satisfy = 'all'
        if 'satisfy' in config:
            if config['satisfy'] in ['any', 'all']:
                satisfy = config['satisfy']
            else:
                raise Exception(
                    'invalid satisfy value: %s' % config['satisfy']
                )

        ipfilter = []
        if 'ipfilter' in config:
            for ip in config['ipfilter']:
                ipfilter.append('allow ' + ip + ';')
            ipfilter.append('deny all;')

        basic_auth = ''
        if 'basic_auth' in config:
            index += 1
            gen_htpasswd(config['basic_auth'], str(index))
            basic_auth = (
                'auth_basic "Restricted";\n'
                'auth_basic_user_file ROOT/nginx/.htpasswd%s;'
                % str(index)
            )

        client_cert = ''
        if 'client-cert' in config:
            client_cert = 'auth_request /client-cert-check-internal;'

        result += """
location %s {
    if ($request_uri ~ ^/(.*\.(css|js)|forms/.*|img/.*|pages/.*)\?[0-9]+$) {
        expires 1y;
    }
    proxy_pass http://mendix;
    satisfy %s;
    %s
    %s
    %s
}
        """ % (
            path,
            satisfy,
            '\n        '.join(ipfilter),
            client_cert,
            basic_auth,
        )
    return '\n    '.join(result.split('\n'))

if __name__ == '__main__':
    print get_path_config()
