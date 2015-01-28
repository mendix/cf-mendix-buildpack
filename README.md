Run Mendix in Cloud Foundry or Heroku
=====


Cloud Foundry
----


### Install cloud foundry command line

Install the Cloud Foundry command line executable. You can find them on the [releases page](https://github.com/cloudfoundry/cli#stable-release).


### Push your app

We simply push an mda (Mendix Deployment Archive) to Cloud Foundry.

    cf push <YOUR_APP> -b https://github.com/mendix/cf-mendix-buildpack -p <YOUR_MDA>.mda

The first push generates a new app, but deployment will fail because the buildpack requires an `ADMIN_PASSWORD` variable and a connected PostgreSQL or MySQL service. So go ahead and set this up after the first failed push.

Keep in mind that the admin password should comply with the policy you have set in the Modeler.

    cf set-env <YOUR_APP> ADMIN_PASSWORD "<YOURSECRETPASSWORD>"

You also need to connect a PostgreSQL or MySQL instance which allows more than 5 connections to the database. Find out which services are available in your Cloud Foundry setup like this.

    cf marketplace

In our trial we found the service `elephantsql` which offered the free `turtle` plan. All you need to do is give it a name and bind it to your application.

    cf create-service elephantsql turtle <SERVICE_NAME>

    cf bind-service <YOUR_APP> <SERVICE_NAME>

Now we need to push the application once more.

    cf push <YOUR_APP> -b https://github.com/mendix/cf-mendix-buildpack -p <YOUR_MDA>.mda

You can now log in to your application with the specified password


### Configuring Constants

The default values for constants will be used as defined in your project. However, you can override them with environment variables. You need to replace the dot with an underscore and prefix it with `MX_`. So a constant like `Module.Constant` with value `ABC123` could be set like this:

    cf set-env <YOUR_APP> MX_Module_Constant "ABC123"

After changing environment variables you need to restart your app. A full push is not necessary.

    cf restart <YOUR_APP>

### Configuring the Java heap size

The default java heap size is set to the total available memory divided by two. If your application's memory limit is 1024M, the heap size is set to 512M. You might want to tweak this to your needs by using another environment variable in which case it is used directly.

    cf set-env <YOUR_APP> HEAP_SIZE 512M


Heroku
----

### Install heroku command line

Install the [https://toolbelt.heroku.com/] (Heroku toolbelt)

### Push your app

Create a new app with a postgres service attached.

    mkdir my-heroku-deployment-dir
    cd my-heroku-deployment-dir
    git init
    heroku create <YOUR_APP> --addons heroku-postgresql:dev --buildpack https://github.com/mendix/cf-mendix-buildpack

Now set up an admin password for your application.

Keep in mind that the admin password should comply with the policy you have set in the Modeler.

    heroku config:set "ADMIN_PASSWORD=<YOURSECRETPASSWORD>"

Deploying is tricky, you should create a git repository where you unpack mda's into. Then you commit everything once you deploy and do git push.

    cd my-heroku-deployment-dir
    rm * -r
    unzip <SOME_MDA>.mda
    git add .
    git commit -a
    git push heroku master

You can now log in to your application with the specified password


### Configuring Constants

The default values for constants will be used as defined in your project. However, you can override them with environment variables. You need to replace the dot with an underscore and prefix it with `MX_`. So a constant like `Module.Constant` with value `ABC123` could be set like this:

    heroku config:set "MX_Module_Constant=ABC123"


### Configuring the Java heap size

The default java heap size is set to the total available memory divided by two. If your application's memory limit is 1024M, the heap size is set to 512M. You might want to tweak this to your needs by using another environment variable in which case it is used directly.

    heroku config:set "HEAP_SIZE=512M"
