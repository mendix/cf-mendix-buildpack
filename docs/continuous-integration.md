Continuous Integration
=====

Login as an Admin user to CF and execute the following with the order:

    cf create-org ci
    cf target -o ci
    cf create-space buildpack
    pwgen -1 30
    cf create-user ci@mendix.net <<pwgen_output>>
    cf set-org-role ci@mendix.net ci OrgManager
    cf set-space-role ci@mendix.net ci buildpack SpaceManager
    cf set-space-role ci@mendix.net ci buildpack SpaceDeveloper
    cf enable-service-access PostgreSQL -o ci
    cf enable-service-access amazon-s3 -o ci
    cf enable-service-access schnapps -o ci
