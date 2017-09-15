Run Mendix in Cloud Foundry
=====
[![Build Status](https://travis-ci.org/mendix/cf-mendix-buildpack.svg?branch=master)](https://travis-ci.org/mendix/cf-mendix-buildpack)

There are specific guides for deploying Mendix apps to the [Pivotal](https://docs.mendix.com/deployment/cloud-foundry/deploy-a-mendix-app-to-pivotal) and [IBM Bluemix](https://docs.mendix.com/deployment/cloud-foundry/deploy-a-mendix-app-to-ibm-bluemix) Cloud Foundry platforms on our [documentation page](https://docs.mendix.com/deployment/cloud-foundry). This buildpack readme documents the more low-level details and CLI instructions.


Deploying using the CLI
----


### Install cloud foundry command line

Install the Cloud Foundry command line executable. You can find this on the [releases page](https://github.com/cloudfoundry/cli#stable-release). Set up the connection to your preferred Cloud Foundry environment with `cf login` and `cf target`.


### Push your app

We push an mda (Mendix Deployment Archive) that was built by the Mendix Business Modeler to Cloud Foundry.

    cf push <YOUR_APP> -b https://github.com/mendix/cf-mendix-buildpack -p <YOUR_MDA>.mda -t 300

We can also push a project directory. This will move the build process (using mxbuild) to Cloud Foundry:

    cd <PROJECT DIR>; cf push -b https://github.com/mendix/cf-mendix-buildpack -t 300

Note that you might need to increase the startup timeout to prevent the database from being partially synchronized. This can be done either by specifying the `-t 300` parameter like above, or by using the `CF_STARTUP_TIMEOUT` environment variable (in minutes) from the command line.

Also note that building the project in Cloud Foundry takes more time and requires enough memory in the compile step.


### Configuring admin password

The first push generates a new app. In order to login to your application as admin you can set the password using the `ADMIN_PASSWORD` environment variable. Keep in mind that the admin password should comply with the policy you have set in the Modeler.

    cf set-env <YOUR_APP> ADMIN_PASSWORD "<YOURSECRETPASSWORD>"


### Connecting a Database

You also need to connect a PostgreSQL or MySQL instance which allows at least 5 connections to the database. Find out which services are available in your Cloud Foundry instance like this.

    cf marketplace

In our trial we found the service `elephantsql` which offered the free `turtle` plan. All you need to do is give it a name and bind it to your application.

    cf create-service elephantsql turtle <SERVICE_NAME>

    cf bind-service <YOUR_APP> <SERVICE_NAME>

Note that not all database service set a `DATABASE_URL` value. If this is not done automatically you need to set this variable manually using the details included in the service, as the buildpack will look for this variable for the database connection string.

Now we need to push the application once more.

    cf push <YOUR_APP> -b https://github.com/mendix/cf-mendix-buildpack -p <YOUR_MDA>.mda

You can now log in to your application with the specified password.


### Configuring Constants

The default values for constants will be used as defined in your project. However, you can override them with environment variables. You need to replace the dot with an underscore and prefix it with `MX_`. So a constant like `Module.Constant` with value `ABC123` could be set like this:

    cf set-env <YOUR_APP> MX_Module_Constant "ABC123"

After changing environment variables you need to restart your app. A full push is not necessary.

    cf restart <YOUR_APP>


### Configuring Scheduled Events

The scheduled events can be configured using environment variable `SCHEDULED_EVENTS`.

Possible values are `ALL`, `NONE` or a comma separated list of the scheduled events that you would like to enable. For example: `ModuleA.ScheduledEvent,ModuleB.OtherScheduledEvent`

When scaling to multiple instances, the scheduled events that are enabled via the settings above will only be executed on instance `0`. The other instances will not execute scheduled events at all.


### Configuring External Filestore

Mendix supports multiple external file stores: AWS S3 compatible file stores (5.15+), Azure Storage (6.6+) and Swift, used in Bluemix Object Storage (6.7+). All of these can be configured manually via [Custom Runtime Settings](#configuring-custom-runtime-settings), but S3, Azure Storage and Swift (Bluemix Object Storage) can be configured in easier ways:

#### Swift (Bluemix Object Storage) Settings

When deploying Mendix 6.7 or higher to Bluemix, you can simply create an [Object Storage service](https://console.ng.bluemix.net/catalog/services/object-storage) and attach it to your app. No further configuration in necessary, you just need to restart your app. By default, a storage container will be created for you called `mendix`. If you want to use a different container name (for example if you are sharing the Object Storage service between multiple apps), you can configure the container name with the environment variable `SWIFT_CONTAINER_NAME`.

#### Azure Storage Service Settings

When deploying Mendix 6.7 or higher to CF on Azure with the Azure Service Broker, you can simply create an Azure Storage Service instance and attach it to your app. No further configuration in necessary, you just need to restart your app. By default, a storage container will be created for you called `mendix`. If you want to use a different container name (for example if you are sharing the Azure Storage service between multiple apps), you can configure the container name with the environment variable `AZURE_CONTAINER_NAME`.

#### S3 Settings

Mendix 5.15 and up can use external file stores with an S3 api. Use the following environment variables to enable this.

* `S3_ACCESS_KEY_ID`: credentials access key
* `S3_SECRET_ACCESS_KEY`: credentials secret
* `S3_BUCKET_NAME`: bucket name

The following environment variables are optional:
* `S3_PERFORM_DELETES`: set to `false` to never delete items from the filestore. This is useful when you use a highly redundant service without a separate backup mechanism, such as AWS S3.
* `S3_KEY_SUFFIX`: if your bucket is multi-tenant you can append a string after each object name, you can restrict IAM users to objects with this suffix.
* `S3_ENDPOINT`: for S3 itself this is not needed, for S3 compatible object stores set the domain on which the object store is available.
* `S3_USE_V2_AUTH`: use Signature Version 2 Signing Process, this is useful for connecting to S3 compatible object stores like Riak-CS, or Ceph.
* `S3_ENCRYPTION_KEYS`: a [JSON string](example-s3-encryption-keys.json) containing a list of keys which can be used to encrypt and decrypt data at rest in S3.
* `S3_USE_SSE`: if set to `true` this will enable Server Side Encryption in S3, available from Mendix 6.0


### Configuring the Java heap size

The default java heap size is set to the total available memory divided by two. If your application's memory limit is 1024M, the heap size is set to 512M. You might want to tweak this to your needs by using another environment variable in which case it is used directly.

    cf set-env <YOUR_APP> HEAP_SIZE 512M


### Configuring the Java version

The default Java version is 8 for Mendix 5.18 and higher. If you want to force Java 7 or 8, you can set the environment variable `JAVA_VERSION` to `7` or `8`.

    cf set-env <YOUR_APP> JAVA_VERSION 8


### Configuring Custom Runtime Settings

To configure any of the advanced [Custom Runtime Settings](https://world.mendix.com/display/refguide6/Custom+Settings) you can use setting name prefixed with `MXRUNTIME_` as an environment variable.

For example, to configure the `ConnectionPoolingMinIdle` setting to value `10`, you can set the following environment variable:

    cf set-env <YOUR_APP> MXRUNTIME_ConnectionPoolingMinIdle 10

If the setting contains a dot `.` you can use an underscore `_` in the environment variable. So to set `com.mendix.storage.s3.EndPoint` to `foo` you can use:

    cf set-env <YOUR_APP> MXRUNTIME_com_mendix_storage_s3_EndPoint foo


### Horizontal Scaling

There are two ways for horizontal scaling in Mendix. In Mendix 5.15+ you can use sticky sessions. Mendix 7 brings this even further by no longer requiring a state store. See below on how to activate these settings, based on the Mendix version you use.

#### Things to keep in mind when scaling horizontally

When you make changes to your domain model, the Mendix Runtime will need to synchronize data model changes with the database on startup. This will only happen on instance `0`. The other instances will wait until the database is fully synchronized. This is determined via the `CF_INSTANCE_INDEX` environment variable. This is a built-in variable in Cloud Foundry, you do not need to set it yourself. If the environment variable is not present (this is the case older Cloud Foundry versions) every instance will attempt to synchronize the database. A warning containing the text `CF_INSTANCE_INDEX environment variable not found` will be printed in the log.

Scheduled events will also only be executed on instance `0`, see the section [Configuring Scheduled Events](#configuring-scheduled-events).

In all horizontal scaling scenarios, extra care needs to be taken when programming Java actions. Examples of things to be avoided are:
* relying on singleton variables to keep global application state
* relying on scheduled events to make changes in memory, scheduled events will only run on the primary instance

#### Enabling Sticky Sessions (Mendix 5.15+)

If you want to enable sticky sessions, the only change that is needed is to set the environment variable `ENABLE_STICKY_SESSIONS` to `true`. This will replace the Mendix session cookie name from `XASSESSIONID` to `JSESSIONID` which will trigger sticky session detection in the Cloud Foundry http router. Watch out: custom login code might break if it still injects the `XASSESSIONID` cookie.

When using sticky sessions, clients need to support http cookies. Webservice integrations typically don't do this, so each request can end up on a different instance.

With sticky sessions there is an increase in resiliency. If one instance crashes, only 1/n-th of the users will be affected. These users will lose their session state and will have to sign in again.

#### Configuring Clustering for Mendix 7

Mendix 7 makes it easier to scale out. The absence of the need for a state store results in the fact that nothing needs to be configured for running Mendix 7 in clustering mode. Based on the `CF_INSTANCE_INDEX` variable, the runtime starts either in leader or slave mode. The leader mode will do the database synchronization activities (when necessary), while the slaves will automatically wait until that is finished.

NOTE: The previously documented setting `CLUSTER_ENABLED` and the REDIS related settings for Mendix 6 will have no effect anymore in Mendix 7 and are ignored.

### Offline buildpack settings

If you are running Cloud Foundry without a connection to the Internet, you should specify an on-premises web server that hosts Mendix Runtime files and other buildpack resources. You can set the endpoint with the following environment variable:

`BLOBSTORE: https://my-intranet-webserver.my-company.com/mendix/`

The preferred way to set up this on-premises web server is as a transparant proxy to `https://cdn.mendix.com/`. This prevents manual work by system administrators every time a new Mendix version is released.

Alternatively you can make the required mendix runtime files `mendix-VERSION.tar.gz` available under `BLOBSTORE/runtime/`. The original files can be downloaded from `https://cdn.mendix.com/`. You should also make the Java version available on:
* `BLOBSTORE/mx-buildpack/jre-8-linux-x64.tar.gz`
* `BLOBSTORE/mx-buildpack/jdk-8-linux-x64.tar.gz`

And for [Mendix < 6.6](https://docs.mendix.com/releasenotes/desktop-modeler/6.6#fixes):
* `BLOBSTORE/mx-buildpack/jre-8u51-linux-x64.tar.gz`
* `BLOBSTORE/mx-buildpack/jdk-8u51-linux-x64.tar.gz`


### Certificate Management

To import Certificate Authorities (CAs) into the Java truststore, use the `CERTIFICATE_AUTHORITIES` environment variable.

The contents of this variable should be a concatenated string containing a the additional CAs in PEM format that are trusted. Example:

    -----BEGIN CERTIFICATE-----
    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
    -----END CERTIFICATE-----
    -----BEGIN CERTIFICATE-----
    MIIEcTCCA1mgAwIBAgIJANUE5069bkdvMA0GCSqGSIb3DQEBBAUAMIGBMQswCQYD
    VQQGEwJOTDEVMBMGA1UECBMMWnVpZC1Ib2xsYW5kMRIwEAYDVQQHEwlSb3R0ZXJk
    YW0xEjAQBgNVBAoTCU1lbmRpeCBCVjESMBAGA1UEAxMJTWVuZGl4IENBMR8wHQYJ
    KoZIhvcNAQkBFhBiZWhlZXJAbWVuZGl4Lm5sMB4XDTA1MTEzMDA5MjY1NFoXDTE1
    MTEyODA5MjY1NFowgYExCzAJBgNVBAYTAk5MMRUwEwYDVQQIEwxadWlkLUhvbGxh
    bmQxEjAQBgNVBAcTCVJvdHRlcmRhbTESMBAGA1UEChMJTWVuZGl4IEJWMRIwEAYD
    VQQDEwlNZW5kaXggQ0ExHzAdBgkqhkiG9w0BCQEWEGJlaGVlckBtZW5kaXgubmww
    ggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQCizJkE35dyDUpz2GgZzVdZ
    Rlf/eA9Xe48hx3WFe2sLGO42ngb71qSQutDxfYStCjT17/25JH5URLfTX/9L4WFe
    INj6uX+Lt8W1ODtgVJ+HvgoJH76etpcXggOLsX8GFXhAdZWiwZ7S3rlVJiaVJWSc
    VrZZkzXwK9Y/la4HjGHGVyd52doYBXb3uMJt9Fl1daT7cz11WTTlUiQEHfkRfROZ
    KXN0o7JtBZqwrHsKaloYPfoW/9SlmrlAe4WJV1+WsdPpxzjfI730lpBgaY6XsLHT
    3I+l/BYHJZx+8jBUFhi+0Aj9TX2Xx3Ran7dmB5dezCyLzcgpM31WE3gid+ELzdFd
    AgMBAAGjgekwgeYwHQYDVR0OBBYEFMZSioCtznEB4WO1S/c7x+4VI2YWMIG2BgNV
    HSMEga4wgauAFMZSioCtznEB4WO1S/c7x+4VI2YWoYGHpIGEMIGBMQswCQYDVQQG
    EwJOTDEVMBMGA1UECBMMWnVpZC1Ib2xsYW5kMRIwEAYDVQQHEwlSb3R0ZXJkYW0x
    EjAQBgNVBAoTCU1lbmRpeCBCVjESMBAGA1UEAxMJTWVuZGl4IENBMR8wHQYJKoZI
    hvcNAQkBFhBiZWhlZXJAbWVuZGl4Lm5sggkA1QTnTr1uR28wDAYDVR0TBAUwAwEB
    /zANBgkqhkiG9w0BAQQFAAOCAQEAKdXKdTLlCPfn4vkJzTg+ukD2CSQysTx+24+P
    4BSUKZ+lOHBmhsKia1Zs+upvbHZ7605x2cdpppEiKC+aVQJJZ2X3BrZZq25oYdDg
    Z1LiFonMl7o4oOjVXhVix4T/WbxuGZTLxpdPHJA+SGw7yaA5Fh0uT70bjTeIfVS6
    cTYdfWO9rsrhiSYt4YeCarDCnjO93vxInvog3ydjJB69luTUXXoniaEnFEXPSqqN
    EVSQHw0FN1bNvaA6/zXvdb7E2oFKIYiPylsdeQ6DPgBxht/YMZRlI8p3F2SiEbbe
    yW7wMeYCUfgTNWaSaJd6uYUjj+IP/9+YOkp5pLW5eEAq6YscYA==
    -----END CERTIFICATE-----

Please note, these are two internal Mendix CAs which you should not actually add to your trust store.


Monitoring Tools
====

### New Relic

To enable New Relic, simply bind a New Relic service to this app and settings will be picked up automatically. Afterwards you have to restage your application to enable the New Relic agent.

### AppDynamics

To enable AppDynamics, configure the following environment variables:

    APPDYNAMICS_CONTROLLER_PORT
    APPDYNAMICS_CONTROLLER_SSL_ENABLED
    APPDYNAMICS_CONTROLLER_HOST_NAME
    APPDYNAMICS_AGENT_APPLICATION_NAME
    APPDYNAMICS_AGENT_ACCOUNT_NAME
    APPDYNAMICS_AGENT_ACCOUNT_ACCESS_KEY
    APPDYNAMICS_AGENT_NODE_NAME *
    APPDYNAMICS_AGENT_TIER_NAME

\* The `APPDYNAMICS_AGENT_NODE_NAME` environment variable will be appended with the value of the `CF_INSTANCE_ID` variable. If you use `my-app` for `APPDYNAMICS_AGENT_NODE_NAME`, the AppDynamics agent will be configured as `my-app-0` for instance `0` and `my-app-1` for instance `1`, etc.

If you have any environment variable that starts with `APPDYNAMICS_`, the AppDynamics Java Agent will be configured for your application. At the moment only agent version 4.1.7.1 is available. After configuring these environment variables, restage your app for the agent to be enabled.

Please note that AppDynamics requires Mendix 6.2 or higher.


Data Snapshots
====

If you want to enable initializing your database and files from an existing data snapshot included in the MDA, set the environment variable `USE_DATA_SNAPSHOT` to `true`. Please note: this only works when the database is completely empty. If there are any Mendix tables defined in the database already, the Runtime will refuse the overwrite it. So, if you have ever started an app before setting this environment variable (thereby initializing the database), you will not be able to import a data snapshot.


License Activation
====

To activate a license on your application you need license credentials. These credentials can be obtained by contacting Mendix Support.

```
cf set-env <YOUR_APP> LICENSE_ID <UUID>
cf set-env <YOUR_APP> LICENSE_KEY <LicenseKey>
```

An example `UUID` is `aab8a0a1-1370-467e-918d-3a243b0ae160` and `LicenseKey` is a very long base64 string. The app needs to be restarted for the license to be effective.

Logging and Debugging
====

To debug the code of the buildpack itself, set the `BUILDPACK_XTRACE` environment variable to `true`.

### App log levels

From Mendix 6 onwards it is possible to configure log levels using environment variables. This allows getting a better insight in the behavior of your Mendix app. Configuring environment variables happens by adding one or more environment variables starting with the name `LOGGING_CONFIG` (the part of the name after that is not relevant and only used to distinguish between multiple entries if necessary). Its value should be valid JSON, in the format:

    {
      "LOGNODE": "LEVEL"
    }

You can see the available Log Nodes in your application in the Mendix Modeler. The level should be one of:
 * `CRITICAL`
 * `ERROR`
 * `WARNING`
 * `INFO`
 * `DEBUG`
 * `TRACE`


Example:

    cf set-env <YOUR_APP> LOGGING_CONFIG '{ "<LOG NODE VALUE>": "DEBUG"}'


### Enabling the Mendix Debugger

You can enable the Mendix Debugger by setting a `DEBUGGER_PASSWORD` environment variable. This will enable and open up the debugger for the lifetime of this process and is to be used with caution. The debugger is reachable on https://DOMAIN/debugger/. You can follow the second half of this [How To](https://docs.mendix.com/howto/monitoring-troubleshooting/debug-microflows) to connect with the Mendix Business Modeler. To stop the debugger, unset the environment variable and restart the application.


Contributing
====

Make sure your code complies with pep8 and that no pyflakes errors/warnings are present.

Rebase your git history in such a way that each commit makes one consistent change. Don't include separate "fixup" commits later on.

For new code changes going live, the version has to bumped at the top of `start.py`, and a new tag with that version number needs to be pushed to github.
