Run Mendix in Cloud Foundry
=====

There are specific guides for deploying Mendix apps to the [Pivotal Web Services](https://world.mendix.com/display/howto50/Deploying+a+Mendix+App+to+Pivotal) and [HP Helion Development Platform](https://world.mendix.com/display/howto50/Deploying+a+Mendix+App+to+HP+Helion) flavors of Cloud Foundry on our [documentation page](https://world.mendix.com/display/howto50/Deploying+a+Mendix+App+to+Cloud+Foundry). This page will document the more low-level details and CLI instructions.


Deploying using the CLI
----


### Install cloud foundry command line

Install the Cloud Foundry command line executable. You can find this on the [releases page](https://github.com/cloudfoundry/cli#stable-release). Set up the connection to your preferred Cloud Foundry environment with `cf login` and `cf target`.


### Push your app

You can push an mda (Mendix Deployment Archive) that was built by the Mendix Business Modeler to Cloud Foundry.

    cf push <YOUR_APP> -b https://github.com/mendix/cf-mendix-buildpack -p <YOUR_MDA>.mda

Or the folder containing an mda:

    cd <MDA DIR>; cf push <YOUR_APP> -b https://github.com/mendix/cf-mendix-buildpack

You can also push a project directory. This will move the build process (using mxbuild) to Cloud Foundry:

    cd <PROJECT DIR>; cf push <YOUR_APP> -b https://github.com/mendix/cf-mendix-buildpack

Note that building the project in Cloud Foundry takes more time and requires enough memory in the compile step.

Additionally, it's possible to provide the Mendix Runtime with your app. This prevents the BuildPack to download the corresponding Mendix Runtime version from the CDN. It als forces your app to be run with that runtime. To achieve that, publish a folder containing an mda or project directory with a folder named `runtimes` inside it. This `runtimes` folder should contain a folder with a Mendix Runtime version having at least the subfolder `runtime` in it. Additionally it is possible to provide the MxBuild version as well by also including the `modeler` folder.

### Configuring admin password

The first push generates a new app, but deployment will fail because the buildpack requires an `ADMIN_PASSWORD` variable and a connected PostgreSQL or MySQL service. So go ahead and set this up after the first failed push.

Keep in mind that the admin password should comply with the policy you have set in the Modeler.

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


### Configuring External Filestore

Mendix 5.15 and up can use external file stores with an S3 api. Use the following environment variables to enable this.

* `S3_ACCESS_KEY_ID`: credentials access key
* `S3_SECRET_ACCESS_KEY`: credentials secret
* `S3_BUCKET_NAME`: bucket name

The following environment variables are optional:
* `S3_PERFORM_DELETES`: set to `false` to never delete items from the filestore. This is useful when you use the filestore without a backup mechanism.
* `S3_KEY_SUFFIX`: if your bucket is multi-tenant you can append a string after each object name, you can restrict IAM users to objects with this suffix.
* `S3_ENDPOINT`: for S3 itself this is not needed, for S3 compatible object stores set the domain on which the object store is available.
* `S3_USE_V2_AUTH`: use Signature Version 2 Signing Process, this is useful for connecting to S3 compatible object stores like Riak-CS, or Ceph.
* `S3_ENCRYPTION_KEYS`: a [JSON string](example-s3-encryption-keys.json) containing a list of keys which can be used to encrypt and decrypt data at rest in S3.


### Configuring the Java heap size

The default java heap size is set to the total available memory divided by two. If your application's memory limit is 1024M, the heap size is set to 512M. You might want to tweak this to your needs by using another environment variable in which case it is used directly.

    cf set-env <YOUR_APP> HEAP_SIZE 512M


### Configuring the Java version

The default Java version is 7. If you want to run on Java 8, you can set the environment variable `JAVA_VERSION` to `8`.

    cf set-env <YOUR_APP> JAVA_VERSION 8


### Enabling the Mendix Debugger

You can enable the Mendix Debugger by setting a `DEBUGGER_PASSWORD` environment variable. This will enable and open up the debugger for the lifetime of this process and is to be used with caution. The debugger is reachable on https://DOMAIN/debugger/. You can follow the second half of this [How To](https://world.mendix.com/display/howto50/Debugging+Microflows+Remotely) to connect with the Mendix Business Modeler. To stop the debugger, unset the environment variable and restart the application.


### Enabling sticky sessions

Mendix apps in version 5.15 and up will automatically set `JSESSIONID` as the session cookie. In most Cloud Foundry configurations this will automatically enable session stickiness, which is required for running Mendix apps with more than one instance. For some distributions you might need to explicitly enable session stickiness in the HTTP router.

If you want to disable the session stickiness, you can set the environment variable `DISABLE_STICKY_SESSIONS` to `true`.


### Configuring Cluster Support (BETA feature for Mendix 6)

From Mendix 6 onwards it is possible to configure clustering support. With clustering support it is possible to run multiple instances of your application to achieve High Availability. Clustering support can be enabled by setting the environment variable `CLUSTER_ENABLED` to `true`.

To optimize performance it is possible to choose for REDIS as State Storage. To use that, add the `RedisCloud` service to your application and configure Mendix to use REDIS for State Storage by setting the environment variable `CLUSTER_STATE_IMPLEMENTATION` to `redis`. In case your selected REDIS service has limited connections available, configure the maximum amount of connections that REDIS can allocate per Mendix Business Server instance by setting the environment variable `CLUSTER_STATE_REDIS_MAX_CONNECTIONS` to the amount of connections available in your plan divided by the amount of instances you want to run.

NOTE: Clustering support is a BETA feature and as such not supported by Mendix for production usage. Settings and implementations may be changed in future releases!

NOTE: Enabling clustering support will automatically disable sticky sessions


Contributing
===

Make sure your code complies with pep8 and that no pyflakes errors/warnings are present.

Rebase your git history in such a way that each commit makes one consistent change. Don't include separate "fixup" commits later on.
