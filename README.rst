bigsudo: Obscene ansible runner
===============================

Bigsudo is an opinionated command line wrapper to ansible-playbook.

It accepts as first argument: role name, path or url, or playbook path
or url::

    bigsudo role.name # download role and run tasks/main.yml on localhost

    bigsudo role.name update # do tasks/update.yml
    bigsudo role.name user@host update # do tasks/update.yml on host
    bigsudo role.name @host update # with current user
    bigsudo role.name @host update foo=bar # custom variable
    bigsudo role.name {"foo":"bar"} # also accepts json without space
    bigsudo role.name --become # forwards any ansible-playbook argument

Note that bigsudo will automatically call ansible-galaxy install on
requirements.yml it finds in any role, recursively on each role that it got
galaxy to install. This means that yourlabs.docker/requirements.yml will also
be installed by bigsudo if your repo has this requirements.yml::

    - src: git+https://yourlabs.io/oss/yourlabs.docker

The gotcha is that you cannot pass values to a short-written argument (because
it's my opinion that ansible commands are more readable as such), ie::

    # works:
    $ ./example/playbook.yml --tags=foo
    ansible-playbook --tags=foo -c local -i localhost, -e apply_tasks='["main"]' ./example/playbook.yml

    # does NOT work: parser doesn't detect that foo is the value of -t:
    $ ./example/playbook.yml -t foo
    ansible-playbook -t -c local -i localhost, -e apply_tasks='["foo"]' ./example/playbook.yml

    # does NOT work: parser doesn't detect that foo is the value of --tags:
    $ ./example/playbook.yml --tags foo
    ansible-playbook --tags -c local -i localhost, -e apply_tasks='["foo"]' ./example/playbook.yml

Using gitlab-ci you can define multiline env vars, ie a with
$STAGING_HOST=deploy@yourstaging and json string for $STAGING_VARS::

    {
      "security_salt": "yoursecretsalf",
      "mysql_password": "...",
      // ....
    }

Then you can define a staging deploy job as such in .gitlab-ci.yml::

    image: yourlabs/python

    # example running tasks/update.yml, using the repo as role
    script: bigsudo . update $STAGING_HOST $STAGING_VARS

    # example running playbook update.yml
    script: bigsudo ./update.yml $STAGING_HOST $STAGING_VARS
