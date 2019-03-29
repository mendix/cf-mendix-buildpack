# Overview of supported VCAP schemas

Using Cloud Foundry database services are detected from VCAP bindings and translated into Mendix M2EE configuration. In case no database service is bound the fallback is the environment variable `DATABASE_URL`.

All database configuration code can be found in `lib/database_config.py`. VCAP service bindings have preference over `DATABASE_URL`. VCAP are recognized on the identifier and/or tags.

## Postgres using RDS Service Broker

Selection based on tags `["database", "RDS", "postgresql"]`.

```
  "rds": [
   {
    "binding_name": null,
    "credentials": {
     "db_name": "databasename",
     "host": "hostname.local",
     "password": "password",
     "uri": "postgres://username:password@hostname.local:5432/databasename",
     "username": "username"
    },
    "instance_name": "03E2080E-BA38-4AD4-B3AC-5F2D7ED2483B-database",
    "label": "rds",
    "name": "03E2080E-BA38-4AD4-B3AC-5F2D7ED2483B-database",
    "plan": "rds-plan",
    "provider": null,
    "syslog_drain_url": null,
    "tags": [
     "database",
     "RDS",
     "postgresql"
    ],
    "volume_mounts": []
   }
  ]
```

## SAP Hana using Service Broker

Selection based on name `hana` and tags `["hana", "database", "relational"]`.

```
  "hana": [
   {
    "binding_name": null,
    "credentials": {
     "certificate": "-----BEGIN CERTIFICATE-----\n<<certficate>>\n-----END CERTIFICATE-----\n",
     "driver": "com.sap.db.jdbc.Driver",
     "host": "hostname",
     "password": "password",
     "port": "21863",
     "schema": "USR_username",
     "url": "jdbc:sap://hostname:21863?encrypt=true\u0026validateCertificate=true\u0026currentschema=USR_username",
     "user": "USR_username"
    },
    "instance_name": "Hana Schema",
    "label": "hana",
    "name": "Hana Schema",
    "plan": "schema",
    "provider": null,
    "syslog_drain_url": null,
    "tags": [
     "hana",
     "database",
     "relational"
    ],
    "volume_mounts": []
   }
  ],
```
