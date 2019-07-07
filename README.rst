bigsudo: Obscene ansible runner
===============================

Bigsudo is an opinionated command line wrapper to ansible-playbook.

Features
--------

It accepts as first argument: role name, path or url, or playbook path
or url::

    bigsudo role.name # download role and run tasks/main.yml on localhost

    bigsudo role.name update # do tasks/update.yml
    bigsudo role.name user@host update # do tasks/update.yml on host
    bigsudo role.name @host update # with current user
    bigsudo role.name @host update foo=bar # custom variable
    bigsudo role.name {"foo":"bar"} # also accepts json without space
    bigsudo role.name -v # forwards any ansible-playbook argument

Note that bigsudo will automatically call ansible-galaxy install on
requirements.yml it finds in any role, recursively on each role that it got
galaxy to install. This means that yourlabs.docker/requirements.yml will also
be installed by bigsudo if your repo has this requirements.yml::

    - src: git+https://yourlabs.io/oss/yourlabs.docker

How command line parsing works
------------------------------

Two golden rules:

- Bigsudo runs with ``--become`` by default (well, it's "bigsudo"), to avoid
  this, pass ``--nosudo``.  This is just because personnaly I am root and
  forget ``--become`` **a lot** more often than I need ``--nosudo``.
- **Bigsudo will take bigsudo arguments first**, they don't start with a dash,
  they are either strings without ``=`` which means they are positionnal
  arguments to bigsudo Python functions, either strings with ``=`` which means
  they are keyword arguments to bigsudo commands.
- From the point where an argument starts with a dash, all arguments are
  forwarded to ansible. **You cannot pass a bigsudo argument after passing an
  argument that starts with a dash**.

As such, these two calls are equivalent::

   bigsudo yourlabs.fqdn -e foo=bar
   bigsudo yourlabs.fqdn foo=bar

But that will not work::

   bigsudo yourlabs.fqdn -v foo=bar

Because it will generate that command in which ansible will look for
``foo=bar`` playbook::

   ansible-playbook -v foo=bar ...

Bigsudo will always print out generated ansible-playbook command lines anyway.

Continuous Deployment with Gitlab-CI
------------------------------------

Using gitlab-ci or drone-ci you can define multiline env vars, ie a with
$STAGING_HOST=deploy@yourstaging and json string for $STAGING_VARS::

    {
      "security_salt": "yoursecretsalf",
      "mysql_password": "...",
      // ....
    }

Then you can define a staging deploy job as such in .gitlab-ci.yml::

    image: yourlabs/python

    # example running tasks/update.yml, using the repo as role
    script: bigsudo . update $staging_host $staging_vars

    # example running playbook update.yml
    script: bigsudo ./update.yml $staging_host $staging_vars

This chapter describes the steps to setup the following deploy job in your
.gitlab-ci.yml::

  deploy-staging:
    image: yourlabs/python
    stage: deploy

    script:
    - mkdir -p ~/.ssh; echo $staging_key > ~/.ssh/id_ed25519; echo $staging_fingerprint > ~/.ssh/known_hosts; chmod 700 ~/.ssh; chmod 600 ~/.ssh/*
    - bigsudo . $staging_host --extra-vars=$staging_vars

    only:
      refs: [master]

    environment:
      name: staging
      url: https://staging.example.com

Create an ed25519 deploy key with the following command::

    ssh-keygen -t ed25519 -a 100 -f deploy.key

Upload the deployment key to your target::

    ssh-copy-id -i deploy.key user@staging.host

Add it to the enviromnent variable ``$staging_key`` ::

    cat deploy.key

Also add your host fingerprint in ``$staging_fingerprint``::

    ssh-keyscan staging.host

Add all the variables you need for your tasks in the ``$staging_vars`` env var
as a JSON dict, as described in the previous chapter.
