# Run Mendix in Cloud Foundry

![Integration Test Status](https://github.com/mendix/cf-mendix-buildpack/workflows/Run%20Integration%20Tests/badge.svg?branch=develop) [![Known Vulnerabilities](https://snyk.io/test/github/mendix/cf-mendix-buildpack/badge.svg)](https://snyk.io/test/github/mendix/cf-mendix-buildpack)

This document contains general information on the Mendix Cloud Foundry Buildpack.

The latest [release](https://github.com/mendix/cf-mendix-buildpack/releases/latest) supports Mendix versions 7 (LTS), 8 (LTS) and 9 (MTS). See the table which buildpack release introduced support for a Mendix version, and in which release versions [are end-of-support](https://docs.mendix.com/releasenotes/studio-pro/lts-mts). [This section](#buildpack-releases-and-version-pinning) describes how to use a specific release.

| Mendix Version | Supported | End-of-Support |
| ---- | ---- | ---- |
| `9.6.x` ([MTS](https://docs.mendix.com/releasenotes/studio-pro/lts-mts)), `9 > 9.6` ([monthly](https://docs.mendix.com/releasenotes/studio-pro/lts-mts)) | `v4.24.0` | - |
| `9 < 9.6.x` | `v4.16.0` | `v4.24.0` |
| `8.18.x` ([LTS](https://docs.mendix.com/releasenotes/studio-pro/lts-mts)) | `v3.4.0` | - |
| `8 < 8.x` | `v3.4.0` | `v4.16.0` |
| `7.23.x` ([LTS](https://docs.mendix.com/releasenotes/studio-pro/lts-mts)) | `v3.1.0` | - |
| `6.x` , `7 < 7.23.x` | `v1.0` | `v4.16.0` |

The buildpack is heavily tied to the Mendix Public Cloud, but can be used independently.
Release notes are available for the [buildpack](https://github.com/mendix/cf-mendix-buildpack/releases/), [Mendix itself](https://docs.mendix.com/releasenotes/studio-pro/) and the [Mendix Public Cloud](https://docs.mendix.com/releasenotes/developer-portal/deployment).

## Requirements

The buildpack requires a cluster which supports the `cflinuxfs3` stack.

Additionally, we recommend a base level knowledge of Cloud Foundry. You should at least be familiar with the Cloud Foundry CLI.

## Lifecycle

The buildpack has two main phases:

* `stage` : Fetch the JRE, Mendix Runtime, and nginx and bundle these together with the application model into a Cloud Foundry droplet. This is handled by `buildpack/stage.py` .
* `run` : Start the various processes and run the application. `buildpack/start.py` is for orchestration, the JVM is for executing the Mendix Model, and nginx is used as reverse proxy including handling access restrictions.

The staging phase accepts archives in `.mda` format (Mendix Deployment Archive). There is experimental support for `.mpk` archives (Mendix Project Package). If an `.mpk` file is pushed, `mxbuild` is executed using Mono in the compile phase as well, the run phase stays the same.

## How to Deploy

There are specific guides for deploying Mendix apps to the [Pivotal](https://docs.mendix.com/deployment/cloud-foundry/deploy-a-mendix-app-to-pivotal) and [IBM Bluemix](https://docs.mendix.com/deployment/cloud-foundry/deploy-a-mendix-app-to-ibm-bluemix) Cloud Foundry platforms on our [documentation page](https://docs.mendix.com/deployment/cloud-foundry). This buildpack readme documents the more low-level details and CLI instructions.

### Install Cloud Foundry CLI

Install the Cloud Foundry command line executable. You can find this on the [releases page](https://github.com/cloudfoundry/cli#stable-release). Set up the connection to your preferred Cloud Foundry environment with `cf login` and `cf target` .

### Push your app

We push an MDA (Mendix Deployment Archive) that was built by Mendix Studio Pro to Cloud Foundry.

*Note: please replace `<LINK-TO-BUILDPACK>` in the commands below with a link to the version of the buildpack you are trying to deploy. Please check [this section](#buildpack-releases-and-version-pinning) for details on how to pick a release.*

```shell
cf push <YOUR_APP> -b <LINK-TO-BUILDPACK> -p <YOUR_MDA>.mda -t 180
```

We can also push a project directory. This will move the build process (using MxBuild, a component of Studio Pro) to Cloud Foundry:

```shell
cd <PROJECT DIR>; cf push -b <LINK-TO-BUILDPACK> -t 180
```

Note that you might need to increase the startup timeout to prevent the database from being partially synchronized. This can be done either by specifying the `-t 180` parameter like above, or by using the `CF_STARTUP_TIMEOUT` environment variable (in minutes) from the command line.

Also note that building the project in Cloud Foundry takes more time and requires enough memory in the compile step.

### Configuring admin password

The first push generates a new app. In order to login to your application as admin you can set the password using the `ADMIN_PASSWORD` environment variable. Keep in mind that the admin password should comply with the policy you have set in the Mendix Modeler. For security reasons it is recommended to set this environment variable once to create the admin user, then remove the environment variable and restart the app. Finally log in to the app and change the password via the web interface. Similarly, the setting can be used to reset the password of an administrator.

```shell
cf set-env <YOUR_APP> ADMIN_PASSWORD "<YOURSECRETPASSWORD>"
```

### Connecting a Database

You also need to connect a PostgreSQL, MySQL or any other Mendix supported database instance which allows at least 5 connections to the database. Find out which services are available in your Cloud Foundry foundation with the `marketplace` command.

```shell
cf marketplace
```

In our trial we found the service `elephantsql` which offered the free `turtle` plan. All you need to do is give it a name and bind it to your application.

cf create-service elephantsql turtle <SERVICE_NAME>
cf bind-service <YOUR_APP> <SERVICE_NAME>

Note that not all databases are automatically picked up by the buildpack. If `cf push` returns an error like `Could not parse database credentials` , you need to set the `DATABASE_URL` variable manually or set database [Mendix custom runtime variables](https://docs.mendix.com/refguide/custom-settings) to configure a database. Note these variables need to be prefixed with `MXRUNTIME_` , as per example:

```shell
cf set-env <YOUR_APP> MXRUNTIME_DatabaseType PostgreSQL
cf set-env <YOUR_APP> MXRUNTIME_DatabaseJdbcUrl jdbc:postgresql://host/databasename
cf set-env <YOUR_APP> MXRUNTIME_DatabaseName databasename
cf set-env <YOUR_APP> MXRUNTIME_DatabaseUserName user
cf set-env <YOUR_APP> MXRUNTIME_DatabasePassword password
```

Now we need to push the application once more.

```shell
cf push <YOUR_APP> -b <LINK-TO-BUILDPACK> -p <YOUR_MDA>.mda
```

You can now log in to your application with the configured admin password.

For PostgreSQL we support setting additional parameters in the connection uri retrieved from the VCAP. To set additional JDBC parameters set the `DATABASE_CONNECTION_PARAMS` environment variable as JSON key-value string.

```shell
cf set-env <YOUR_APP> DATABASE_CONNECTION_PARAMS '{"tcpKeepAlive": "true", "connectionTimeout": 30, "loginTimeout": 15}'
```

Note: if you set `DATABASE_URL` provide it as JDBC connection string (prefixed with `jdbc:` and including parameters, `DATABASE_CONNECTION_PARAMS` is not needed then.

### Configuring Constants

The default values for constants will be used as defined in your project. However, you can override them with environment variables. You need to replace the dot with an underscore and prefix it with `MX_` . So a constant like `Module.Constant` with value `ABC123` could be set like this:

```shell
cf set-env <YOUR_APP> MX_Module_Constant "ABC123"
```

After changing environment variables you need to restart your app. A full push is not necessary.

```shell
cf restart <YOUR_APP>
````

### Configuring Scheduled Events

The scheduled events can be configured using environment variable `SCHEDULED_EVENTS` .

Possible values are `ALL` , `NONE` or a comma separated list of the scheduled events that you would like to enable. For example: `ModuleA. ScheduledEvent, ModuleB. OtherScheduledEvent`

When scaling to multiple instances, the scheduled events that are enabled via the settings above will only be executed on instance `0` . The other instances will not execute scheduled events at all.

### Configuring External Filestore

Mendix supports multiple external file stores: AWS S3 compatible file stores, Azure Storage and Swift, used in Bluemix Object Storage. All of these can be configured manually via [Custom Runtime Settings](#configuring-custom-runtime-settings), but S3, Azure Storage and Swift (Bluemix Object Storage) can be configured in easier ways.

#### Swift (Bluemix Object Storage) Settings

When deploying Mendix 6.7 or higher to Bluemix, you can simply create an [Object Storage service](https://console.ng.bluemix.net/catalog/services/object-storage) and attach it to your app. No further configuration in necessary, you just need to restart your app. By default, a storage container will be created for you called `mendix` . If you want to use a different container name (for example if you are sharing the Object Storage service between multiple apps), you can configure the container name with the environment variable `SWIFT_CONTAINER_NAME` .

#### Azure Storage Service Settings

When deploying Mendix 6.7 or higher to CF on Azure with the Azure Service Broker, you can simply create an Azure Storage Service instance and attach it to your app. No further configuration in necessary, you just need to restart your app. By default, a storage container will be created for you called `mendix` . If you want to use a different container name (for example if you are sharing the Azure Storage service between multiple apps), you can configure the container name with the environment variable `AZURE_CONTAINER_NAME` .

#### S3 Settings

Mendix can use external file stores with an S3 compatible api. There are two ways to enable this.

##### Use IAM Credentials

Create an IAM user and provide IAM user credential using following environment variables.

* `S3_ACCESS_KEY_ID` : credentials access key
* `S3_SECRET_ACCESS_KEY` : credentials secret
* `S3_BUCKET_NAME` : bucket name

##### Implement TVM (Token Vending Machine)

Create a TVM (Token Vending Machine) and provide TVM credential using following environment variable.

* `S3_TVM_ENDPOINT` : tvm_endpoint
* `S3_TVM_USERNAME` : tvm_username
* `S3_TVM_PASSWORD` : tvm_password

Please check [s3-tvm-spec](https://github.com/mendix/s3-tvm-spec) for api documentation help for tvm.

The following environment variables are optional:

* `S3_PERFORM_DELETES` : set to `false` to never delete items from the filestore. This is useful when you use a highly redundant service without a separate backup mechanism, such as AWS S3.
* `S3_KEY_SUFFIX` : if your bucket is multi-tenant you can append a string after each object name, you can restrict IAM users to objects with this suffix.
* `S3_ENDPOINT` : for S3 itself this is not needed, for S3 compatible object stores set the domain on which the object store is available.
* `S3_USE_V2_AUTH` : use Signature Version 2 Signing Process, this is useful for connecting to S3 compatible object stores like Riak-CS, or Ceph.
* `S3_USE_SSE` : if set to `true` this will enable Server Side Encryption in S3, available from Mendix 6.0

### Configuring the Java Heap Size

The Java heap size is configured automatically based on best practices. You can tweak this to your needs by using another environment variable in which case it is used directly.

```shell
cf set-env <YOUR_APP> HEAP_SIZE 512M
```

### Configuring the Java Version

The buildpack will automatically determine the Java version to use based on the runtime version of the app being deployed. The default Java version is 8 for Mendix 5.18 and higher. For Mendix 8 and above the default Java version is 11. In most cases it is not needed to change the Java version determined by the buildpack.

*Note*: Starting from Mendix 7.23.1, we changed to use AdoptOpenJDK. The buildpack will automatically determine the vendor based on the Mendix version. The `JAVA_VERSION` variable can be used to select a version number only, not the vendor.

If you want to force Java 7 or 8, you can set the environment variable `JAVA_VERSION` to `7` or `8` :

```shell
cf set-env <YOUR_APP> JAVA_VERSION 8
```

Or to switch patch version for Java 11:

```shell
cf set-env <YOUR_APP> JAVA_VERSION 11.0.3
```

### Customizing the Java Virtual Machine (JVM) Settings

You can configure the Java properties by providing the `JAVA_OPTS` enviroment variable to the application.

Configure the `JAVA_OPTS` environment variable by using the `cf set-env` command.

```shell
cf set-env <YOUR_APP> JAVA_OPTS '["-Djava.rmi.server.hostname=127.0.0.1", "-Dcom.sun.management.jmxremote.authenticate=false", "-Dcom.sun.management.jmxremote.ssl=false", "-Dcom.sun.management.jmxremote.port=5000", "-Dcom.sun.management.jmxremote.rmi.port=5000"]'
```

### Configuring Custom Runtime Settings

To configure any of the advanced [Custom Runtime Settings](https://docs.mendix.com/refguide/custom-settings) you can use setting name prefixed with `MXRUNTIME_` as an environment variable.

For example, to configure the `ConnectionPoolingMinIdle` setting to value `10` , you can set the following environment variable:

```shell
cf set-env <YOUR_APP> MXRUNTIME_ConnectionPoolingMinIdle 10
```

If the setting contains a dot `.` you can use an underscore `_` in the environment variable. So to set `com.mendix.storage.s3.EndPoint` to `foo` you can use:

```shell
cf set-env <YOUR_APP> MXRUNTIME_com_mendix_storage_s3_EndPoint foo
```

### Configuring HTTP Headers

HTTP headers allow the client and the server to pass additional information with the request or the response which defines the operating parameters of an HTTP transaction. Few of the response headers can be configured via `HTTP_RESPONSE_HEADERS` environment variable and setting a JSON string value to configure multiple supported headers. See [Environment Details - Developer Portal Guide | Mendix Documentation Section 4.2](https://docs.mendix.com/developerportal/deploy/environments-details) for all supported headers and options.

For example, to configure `X-Frame-Options` , you can set `HTTP_RESPONSE_HEADERS` environment variable like below:

```shell
cf set-env <YOUR_APP> HTTP_RESPONSE_HEADERS '{"X-Frame-Options": "allow-from https://mendix.com"}'
```

to configure multiple supported headers, you can set it like below:

```shell
cf set-env <YOUR_APP> HTTP_RESPONSE_HEADERS '{"Referrer-Policy": "no-referrer-when-downgrade", "X-Content-Type-Options": "nosniff"}'
```

### Enabling SameSite / Secure Cookie Header Injection for Mendix Runtime < 8.12

Google Chrome will - at a certain moment - [enforce cookie security](https://www.chromium.org/updates/same-site) by requiring the `SameSite` and `Secure` atrributes for all cookies. Mendix runtime versions < 8.12 do not include these properties in cookies.

The buildpack can inject these two properties into all cookies for affected runtime versions.

This workaround is disabled by default. If your application supports injecting these cookies, you can choose to enable cookie header injection by setting the `SAMESITE_COOKIE_PRE_MX812` environment variable to `true` .

### Horizontal Scaling

There are two ways for horizontal scaling in Mendix. In Mendix 6 you can use sticky sessions. Mendix 7 brings this even further by no longer requiring a state store. See below on how to activate these settings, based on the Mendix version you use.

#### Things to keep in mind when scaling horizontally

When you make changes to your domain model, the Mendix Runtime will need to synchronize data model changes with the database on startup. This will only happen on instance `0` . The other instances will wait until the database is fully synchronized. This is determined via the `CF_INSTANCE_INDEX` environment variable. This is a built-in variable in Cloud Foundry, you do not need to set it yourself. If the environment variable is not present (this is the case older Cloud Foundry versions) every instance will attempt to synchronize the database. A warning containing the text `CF_INSTANCE_INDEX environment variable not found` will be printed in the log.

Scheduled events will also only be executed on instance `0` , see the section [Configuring Scheduled Events](#configuring-scheduled-events).

In all horizontal scaling scenarios, extra care needs to be taken when programming Java actions. Examples of things to be avoided are:

* relying on singleton variables to keep global application state
* relying on scheduled events to make changes in memory, scheduled events will only run on the primary instance

#### Enabling Sticky Sessions (Mendix 6)

If you want to enable sticky sessions, the only change that is needed is to set the environment variable `ENABLE_STICKY_SESSIONS` to `true` . This will replace the Mendix session cookie name from `XASSESSIONID` to `JSESSIONID` which will trigger sticky session detection in the Cloud Foundry http router. Watch out: custom login code might break if it still injects the `XASSESSIONID` cookie.

When using sticky sessions, clients need to support http cookies. Webservice integrations typically don't do this, so each request can end up on a different instance.

With sticky sessions there is an increase in resiliency. If one instance crashes, only 1/n-th of the users will be affected. These users will lose their session state and will have to sign in again.

#### Configuring Clustering for Mendix 7

Mendix 7 makes it easier to scale out. The absence of the need for a state store results in the fact that nothing needs to be configured for running Mendix 7 in clustering mode. Based on the `CF_INSTANCE_INDEX` variable, the runtime starts either in leader or slave mode. The leader mode will do the database synchronization activities (when necessary), while the slaves will automatically wait until that is finished.

NOTE: The previously documented setting `CLUSTER_ENABLED` and the REDIS related settings for Mendix 6 will have no effect anymore in Mendix 7 and are ignored.

### Offline Buildpack Settings

If you are running Cloud Foundry without a connection to the Internet, you should specify an on-premises web server that hosts Mendix Runtime files and other buildpack resources. You can set the endpoint with the following environment variable:

 `BLOBSTORE: https://my-intranet-webserver.my-company.com/mendix/`

The preferred way to set up this on-premises web server is as a transparent proxy to `https://cdn.mendix.com/` . This prevents manual work by system administrators every time a new Mendix version is released.

Alternatively you can make the required mendix runtime files `mendix-VERSION.tar.gz` available under `BLOBSTORE/runtime/` . The original files can be downloaded from `https://cdn.mendix.com/` . You should also make the Java version available on:

* `BLOBSTORE/mx-buildpack/jre-8-linux-x64.tar.gz` (Mendix < 8)
* `BLOBSTORE/mx-buildpack/jdk-8-linux-x64.tar.gz` (Mendix < 8)
* `BLOBSTORE/mx-buildpack/jre-11-linux-x64.tar.gz` (Mendix 8)
* `BLOBSTORE/mx-buildpack/jdk-11-linux-x64.tar.gz` (Mendix 8)

And for [Mendix \< 6.6](https://docs.mendix.com/releasenotes/desktop-modeler/6.6#fixes):

* `BLOBSTORE/mx-buildpack/jre-8u51-linux-x64.tar.gz`
* `BLOBSTORE/mx-buildpack/jdk-8u51-linux-x64.tar.gz`

### Managing Certificate Authorities

To import Certificate Authorities (CAs) into the Java truststore, use the `CERTIFICATE_AUTHORITIES` environment variable.

The contents of this variable should be a concatenated string containing a the additional CAs in [PEM format](https://en.wikipedia.org/wiki/Privacy-Enhanced_Mail) that are trusted.

Example:

```plaintext
-----BEGIN CERTIFICATE-----
AaBbCc==
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
DdEeFf==
-----END CERTIFICATE-----
```

Note that if a certificate is signed by an intermediary, the complete certificate chain has to be added.

### Managing Client Certificates

To add client certificates to the Mendix runtime configuration, use the `CLIENT_CERTIFICATES` environment variable.

Example:

```json
[
    {"pfx": "AaBbCc==", "password": "password1", "pin_to": ["Module.WS1", "/bla/bla"]},
    {"pfx": "DdEeFf==", "password": ""}
]
```

The buildpack ensures that the environment variable is converted into custom runtime settings, and client certificate support is dependent on runtime support. Please consult the [runtime documentation](https://docs.mendix.com/howto/integration/use-a-client-certificate) on client certificates for the runtime version of your application for further support.

#### Client Certificate Format

The environment variable is in JSON format and is a list ( `[]` ) of **client certificate objects**. Each object contains the following fields:

| Field | Type | Required | Example | Description |
|-|-|-|-|-|
| `pfx` | `string(base64)` | Yes | `"AaBbCc=="` | Certificate in [PKCS#12 format](https://en.wikipedia.org/wiki/PKCS_12), encoded in `base64` |
| `password` | `string` | Yes | `"password1"` | Certificate password. Can be blank. |
| `pin_to` | `[string]` | No | `["Module.WS1", "/bla/bla"]` | JSON list of Mendix modules or relative paths to pin the client certificate to |

### Managing Access Restrictions

The buildpack proxy has the possibility to set access restrictions for certain application paths. To do so, use the `ACCESS_RESTRICTIONS` environment variable.

Example:

```json
{
    "/": {"ipfilter": ["10.0.0.0/8"], "client_cert": true, "satisfy": "any"},
    "/ws/MyWebService/": {"ipfilter": ["10.0.0.0/8"], "client_cert": true, "satisfy": "all"},
    "/CustomRequestHandler/": {"ipfilter": ["10.0.0.0/8"]},
    "/CustomRequestHandler2/": {"basic_auth": {"user1": "password", "user2": "password2"}},
}
```

#### Access Restrictions Format

The environment variable is in JSON format and is a collection ( `{}` ) of **path restriction objects**. Each object is defined by a `path` (relative to the application root URL). A restriction object applies to that path and all sub-paths. Inheritance can be overridden by adding a restriction object for a sub-path. These settings will then override the parent object.

Note that:

* Access restrictions are not supported for reserved system paths
* A path restriction object must at least contain one restriction object

A path restriction object is composed of the following fields:

| Field | Type | Example | Description |
|-|-|-|-|
| `ipfilter` | `[string]` | `["10.0.0.0/8"]` | List of IPs to allow in [CIDR format](https://en.wikipedia.org/wiki/Classless_Inter-Domain_Routing). An empty list will allow access from all IPs. |
| `client_cert` | `boolean` | `false` | Enables checking client certificates. The certificate for the exact path the restriction applies to must be correctly provided with the [ `CLIENT_CERTIFICATES` environment variable](#managing-client-certificates). |
| `basic_auth` | `{string: string, string: string, ...}` | `{"user1": "password", "user2": "password2"}` | Adds a [HTTP Basic Authentication](https://en.wikipedia.org/wiki/Basic_access_authentication) restriction. Multiple user / password combinations can be supplied in one JSON object. |
| `satisfy` | `string(any\|all)` | `"any"` | Defines how restrictions are evaluated. `any` is equivalent to logical `OR` , `all` to `AND` . |
| `issuer_dn` | `string` | `"CN=example.com,O=example Inc."` | Adds certificate pinning through the `"Ssl-Client-Issuer-Dn"` header. This header must be supplied through an upstream proxy. |

## Monitoring Tools

### New Relic

To enable New Relic, simply bind a New Relic service to this app and settings will be picked up automatically. Afterwards you have to restage your application to enable the New Relic agent.

### AppDynamics

To enable AppDynamics, configure the following environment variables:

```plaintext
APPDYNAMICS_CONTROLLER_PORT
APPDYNAMICS_CONTROLLER_SSL_ENABLED
APPDYNAMICS_CONTROLLER_HOST_NAME
APPDYNAMICS_AGENT_APPLICATION_NAME
APPDYNAMICS_AGENT_ACCOUNT_NAME
APPDYNAMICS_AGENT_ACCOUNT_ACCESS_KEY
APPDYNAMICS_AGENT_NODE_NAME *
APPDYNAMICS_AGENT_TIER_NAME
```

\* The `APPDYNAMICS_AGENT_NODE_NAME` environment variable will be appended with the value of the `CF_INSTANCE_ID` variable. If you use `my-app` for `APPDYNAMICS_AGENT_NODE_NAME` , the AppDynamics agent will be configured as `my-app-0` for instance `0` and `my-app-1` for instance `1` , etc.

If you have any environment variable that starts with `APPDYNAMICS_` , the AppDynamics Java Agent will be configured for your application. At the moment only agent version `21.11.1.33280` is available. After configuring these environment variables, restage your app for the agent to be enabled.

Please note that AppDynamics requires Mendix 6.2 or higher.

### Datadog

The Datadog integration features a limited Datadog Agent installation included in the [official Datadog Cloud Foundry Buildpack](https://github.com/DataDog/datadog-cloudfoundry-buildpack). The following information is collected:

* [Application metrics](https://docs.mendix.com/developerportal/operate/datadog-metrics) are collected by the Datadog IoT agent.
* [JMX metrics](https://docs.datadoghq.com/integrations/java/) and [APM traces](https://docs.datadoghq.com/tracing/setup_overview/setup/java/) are retrieved using the Datadog Java trace agent and collected by the Datadog agent.
* [PostgreSQL metrics](https://github.com/influxdata/telegraf/tree/master/plugins/inputs/postgresql) are collected by an included [Telegraf agent](https://docs.influxdata.com/telegraf/) and sent directly to Datadog via the Datadog API.

To enable Datadog, configure the following environment variables:

| Environment Variable | Description |
|-|-|
| `DD_API_KEY` | The Datadog API key. Can can be configured in the `Integrations -> API` screen of the user interface for your Datadog organization. |
| `DD_LOG_LEVEL` | Ensures that log messages are sent to Datadog. A safe level would be `INFO` , but it can be later adjusted to different levels: `CRITICAL` , `ERROR` , `WARNING` , or `DEBUG` . |

If you're using a Datadog EU organization, you should also set the `DD_SITE` environment variable accordingly.

Additionally, the following integration-specific variables are available:
| Environment Variable | Default Value | Description |
|-|-|-|
| `DATADOG_DATABASE_DISKSTORAGE_METRIC` | `true` | Enables a metric denoting the disk storage size available to the database. This metric is set in the `DATABASE_DISKSTORAGE` environment variable. |
| `DATADOG_DATABASE_RATE_COUNT_METRICS` | `false` | Enables additional rate / count database metrics currently not compatible with the Datadog PostgreSQL integration |
| `DATADOG_LOGS_REDACTION` | `true` | Enables email address redaction from logs |

To receive metrics from the runtime, the Mendix Java Agent is added to the runtime as Java agent. This agent can be configured by passing a JSON in the environment variable `METRICS_AGENT_CONFIG` as described in [Datadog for v4 Mendix Cloud](https://docs.mendix.com/developerportal/operate/datadog-metrics).

Please note that application metric collection **requires Mendix 7.14 or higher**.

#### Presets

For correlation purposes, we set the Datadog `service` for you to match your **application name**. This name is derived in the following order:

1. Your Mendix `service:` tag if you have set this in the runtime settings or `TAGS` environment variable.<br/>*Format:* `["service:myfirstapp", "tag2:value2", ...]`.
2. Your Mendix `app:` tag if you have set this in the runtime settings or `TAGS` environment variable.<br/>*Example:* for `app:myfirstapp` ,  `service` will be set to `myfirstapp`.
3. The first part of the Cloud Foundry route URI configured for your application, without numeric characters.<br/>*Example:* for a route URI `myfirstapp1000-test.example.com` ,  `service` will be set to `myfirstapp` .

Additionally, we configure the following Datadog environment variables for you:

| Environment Variable | Value | Can Be Overridden? | Description |
|-|-|-|-|
| `DD_HOSTNAME` | `<app>-<env>.mendixcloud.com<-instance>` | No | Human-readable host name for your application |
| `DD_ENV` | `<env>` | Yes | Reserved tag. Set to the value of the `env` tag. Defaults to `none` .
| `DD_SERVICE` | `<app>` | Yes | Reserved tag. Set as as described before. Is only set when `DD_TRACE_ENABLED` is set to `true` . |
| `DD_VERSION` | `<model_version>` | Yes | Reserved tag. Set to the value of the `version` tag. Defaults to the Mendix model version of the application. |
| `DD_TAGS` | `tag1:value1,...:...` | Yes | Global tags for Datadog Agent(s). Derived from the runtime settings in Mendix Public Cloud or the `TAGS` environment variable. |
| `DD_TRACE_ENABLED` | `false` | Yes | Enables Datadog APM and the Trace Agent(s). **Enabling Datadog APM is experimental and enables tracing via the [Datadog Java Trace Agent](https://docs.datadoghq.com/tracing/setup/java/) tracing functionality.** |
| `DD_PROFILING_ENABLED` | `false` | Yes | Enables Datadog APM and the Trace Agent(s). **Enabling Datadog Profiling is experimental and can only be enabled for Mendix 7.23.1 and up, and requires tracing to be enabled.** |
| `DD_JMXFETCH_ENABLED` | `true` | No | Enables Datadog Java Trace Agent JMX metrics fetching |
| `DD_SERVICE_MAPPING` | `<database>:<app>.db` | No | Links your database to your app in Datadog APM |
| `DD_LOGS_ENABLED` | `true` | No | Enables sending your application logs directly to Datadog |
| `DD_CHECKS_ENABLED` | `false` | Yes | Enables system metrics. These are disabled by default, as the metrics might be host metrics instead of container metrics. |

Other environment variables can be set as per the [Datadog Agent documentation](https://docs.datadoghq.com/agent/).

#### Known Limitations

Telegraf [does not support (Datadog) metric types correctly yet](https://github.com/influxdata/telegraf/issues/6822) (e.g. rate, counter, gauge). This means that all database metrics are currently pushed to Datadog as a gauge.

The most important metrics ( `before_xid_wraparound` , `connections` , `database_size` , `db.count` , `locks` , `max_connections` , `percent_usage_connections` , `table.count` , `deadlocks` ) are gauges and are compatible with the Datadog PostgreSQL integration and associated dashboards.

*If you do require the additional rate and counter metrics, there is a workaround available.* First, set the `DATADOG_DATABASE_RATE_COUNT_METRICS` environment variable to `true` . After that variable is enabled, the rate and counter metrics are suffixed by either `_count` or `_rate` to prevent collisions with the official Datadog metrics. In the Datadog UI, the [metric type and unit can be changed](https://docs.datadoghq.com/developers/metrics/type_modifiers/?tab=count#modify-a-metrics-type-within-datadog) to reflect this. We also set a helpful `interval` tag ( `10s` ) which can be used here. Additionally, gauge metrics can be [rolled up in Datadog dashboards](https://docs.datadoghq.com/dashboards/functions/rollup/). The correct type and unit for other submitted metrics can be found [here](https://github.com/DataDog/integrations-core/blob/master/postgres/metadata.csv).

### Dynatrace

[Dynatrace SaaS/Managed](http://www.dynatrace.com/cloud-foundry/) is your full stack monitoring solution - powered by artificial intelligence. Dynatrace SaaS/Managed allows you insights into all application requests from the users click in the browser down to the database statement and code-level.

To enable Dynatrace, configure the following environment variables:

| Environment Variable | Description |
|-|-|
| `DT_PAAS_TOKEN` | The token for integrating your Dynatrace environment with Cloud Foundry. You can find it in the deploy Dynatrace section within your environment. |
| `DT_SAAS_URL` | Monitoring endpoint url of the Dynatrace service |
| `DT_TENANT` | Your Dynatrace environment ID is the unique identifier of your Dynatrace environment. You can find it in the deploy Dynatrace section within your environment. |

By setting these environment variables automatically the Dynatrace OneAgent will be loaded in the container. 

OneAgent will be able to measure all J2EE related Metrics from the Application. See OneAgent documention for more details. 

# Data Snapshots

If you want to enable initializing your database and files from an existing data snapshot included in the MDA, set the environment variable `USE_DATA_SNAPSHOT` to `true` . Please note: this only works when the database is completely empty. If there are any Mendix tables defined in the database already, the Runtime will refuse the overwrite it. So, if you have ever started an app before setting this environment variable (thereby initializing the database), you will not be able to import a data snapshot.

# License Activation

To activate a license on your application you need license credentials. These credentials can be obtained by contacting Mendix Support.

```shell
cf set-env <YOUR_APP> LICENSE_ID <UUID>
cf set-env <YOUR_APP> LICENSE_KEY <LicenseKey>
```

An example `UUID` is `aab8a0a1-1370-467e-918d-3a243b0ae160` and `LicenseKey` is a very long base64 string. The app needs to be restarted for the license to be effective.

# Logging and Debugging

To debug the code of the buildpack itself, set the `BUILDPACK_XTRACE` environment variable to `true` .

## App Log Levels

From Mendix 6 onwards it is possible to configure log levels using environment variables. This allows getting a better insight in the behavior of your Mendix app. Configuring environment variables happens by adding one or more environment variables starting with the name `LOGGING_CONFIG` (the part of the name after that is not relevant and only used to distinguish between multiple entries if necessary). Its value should be valid JSON, in the format:

```json
{
    "LOGNODE": "LEVEL"
}
```

You can see the available Log Nodes in your application in the Mendix Modeler. The level should be one of:

* `CRITICAL`
* `ERROR`
* `WARNING`
* `INFO`
* `DEBUG`
* `TRACE`

Example:

```shell
cf set-env <YOUR_APP> LOGGING_CONFIG '{"<LOG NODE VALUE>": "DEBUG"}'
```

## Rate-limiting of Log Output

The buildpack has the ability to rate-limit the amount of log lines from the Mendix Runtime. This can be useful for apps that misbehave and cause problems for other users in a multi-tenant environment. Rate-limiting is done in log lines per second. Extra lines are dropped and the number of dropped messages is printed on `stderr` .

Example (1000 loglines/second):

```shell
cf set-env <YOUR_APP> LOG_RATELIMIT '1000'
```

## Enabling the Mendix Debugger

You can enable the Mendix Debugger by setting a `DEBUGGER_PASSWORD` environment variable. This will enable and open up the debugger for the lifetime of this process and is to be used with caution. The debugger is reachable on https://DOMAIN/debugger/. You can follow the second half of this [How To](https://docs.mendix.com/howto/monitoring-troubleshooting/debug-microflows) to connect with the Mendix Business Modeler. To stop the debugger, unset the environment variable and restart the application.

# Buildpack Releases and Version Pinning

We recommend "pinning to" - using a specific [release](https://github.com/mendix/cf-mendix-buildpack/releases) of - the buildpack. This will prevent you from being affected by bugs that are inadvertently introduced, but you will need to set up a procedure to regularly move to new versions of the buildpack.

To push with a specific release of the buildpack, replace `<RELEASE>` in the buildpack URL below in your `cf push` command with the release you want to pin to, e.g. `v4.11.0` :

```shell
cf push <YOUR_APP> -b https://github.com/mendix/cf-mendix-buildpack/releases/download/<RELEASE>/cf-mendix-buildpack.zip -p <YOUR_MDA>.mda -t 180
```

You can find the list of available releases [here](https://github.com/mendix/cf-mendix-buildpack/releases).

**Note: do not directly pin to the buildpack source code, but always pin to a specific release. The release is a runnable version of the buildpack and always contains the (binary) dependencies needed to run the buildpack directly; we do not guarantee that the source code by itself runs.**

# Troubleshooting (Rescue Mode)

Sometimes the app won't run because it exits with status code 143. Or, for any reason, the app is unable to start, leaving you unable to debug the issue from within the container. For these cases we have introduced a `DEBUG_CONTAINER` mode. To enable it:

```shell
cf set-env <YOUR_APP> DEBUG_CONTAINER true
cf restart <YOUR_APP>
```

Now your app will start in CloudFoundry (i.e. the Mendix Runtime will not start yet) and you can troubleshoot the problem with:

```shell
cf ssh <YOUR_APP>
export HOME=$HOME/app # this should not be needed but for now it is
export DEBUG_CONTAINER=false # while we are in the container turn it off, we could try to make this optional by detecting other environment variables that are present over ssh but not regular start
export PORT=1234 # so that nginx can start correctly
cd app
PYTHONPATH=:buildpack:lib python3 buildpack/start.py
```

After you are done, you can disable debug mode with:

```shell
cf unset-env <YOUR_APP> DEBUG_CONTAINER
cf restart <YOUR_APP>
```

Similarly, if you need to use `m2ee-tools` inside the container for debugging
purposes, you can do the following:

```shell
cf ssh <YOUR_APP>
export PYTHONPATH=/home/vcap/app/.local/lib/python3.6/site-packages/:/home/vcap/app/lib/
python3
```

and in the interactive Python console:

```python
import os
from m2ee.client import M2EEClient
client = M2EEClient('http://localhost:8082', os.environ['M2EE_PASSWORD'])
```

# Limitations

These are known limitations for the Mendix buildpack.

## Using the `cflinuxfs2` root filesystem (stack)

`cflinuxfs2` support was officially removed in version `4.7.0` of this buildpack. Please use an earlier buildpack version if you want to use this stack.

## Pushing MPKs produced by Mendix Studio Pro 6.x

When it is desired to push MPKs produced by Mendix Studio Pro 6.x to containers using `cflinuxfs3` as root filesystem, the staging phase is likely going to fail when the default settings are used. As a workaround, more disk space needs to be allocated for the cache. Consult the [Deploying a Large App](https://docs.cloudfoundry.org/devguide/deploy-apps/large-app-deploy.html) section in the official CloudFoundry documentation for more information.

# Developing and Contributing

Please see [ `DEVELOPING.md` ](DEVELOPING.md) and [ `CONTRIBUTING.md` ](CONTRIBUTING.md).

# License

This project is licensed under the Apache License v2 (for details, see the [ `LICENSE` ](LICENSE) file).
