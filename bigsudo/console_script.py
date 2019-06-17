"""Apply a role or playbook without inventory."""

import cli2
import json
from pathlib import Path
import re
import requests
import shlex
import subprocess
import sys
import os
import yaml


M = '((?P<user>[^@]*)@)?(?P<host>([a-z0-9_-]+\.[^/]*)+)?/?(?P<path>[^/]+/.*)'  # noqa


def _galaxyinstall(*args):
    print(
        subprocess.check_output(
            'ansible-galaxy install ' + ' '.join(args),
            shell=True
        ).decode('utf8')
    )


def reqinstall(reqpath='requirements.yml'):
    """Install requirements recursively."""
    reqpath = str(reqpath)
    _galaxyinstall('--ignore-errors -r', reqpath)

    with open(reqpath, 'r') as f:
        data = yaml.safe_load(f)

    for dependency in data:
        if 'name' in dependency:
            rolename = dependency['name']
        elif 'src' in dependency:
            rolename = dependency['src'].split('/')[-1].rstrip('.git')
        else:
            rolename = dependency

        subreq = os.path.join(
            os.getenv('HOME'),
            '.ansible',
            'roles',
            rolename,
            'requirements.yml',
        )

        if os.path.exists(subreq):
            reqinstall(subreq)


def _argv(*hosts, **variables):
    """Return generated ansible args."""

    verbose = False
    for dasharg in console_script.parser.dashargs:
        if re.match('^v+$', dasharg):
            verbose = True

    if verbose:
        os.environ['ANSIBLE_STDOUT_CALLBACK'] = 'debug'

    argv = ['ansible-playbook'] + [
        arg
        for arg in console_script.parser.argv_all
        if arg.startswith('-')
    ]

    argv += ['-e', 'ansible_python_interpreter=python3']

    hosts = hosts or ('localhost',)

    inv = []
    user = None
    for host in hosts:
        if '@' in host:
            parts = host.split('@')
            if parts[0]:
                user = parts[0]
            inv.append(parts[1])
        else:
            inv.append(host)

    if inv == ['localhost']:
        argv += ['-c', 'local']

    if user:
        argv += ['-u', user]

    if inv:
        argv += ['-i', ','.join(inv) + ',']

    for key, value in variables.items():
        if not isinstance(value, str):
            value = json.dumps(value)
        argv += ['-e', key + '=' + shlex.quote(value)]

    return argv


def roleinstall(role):
    """Install a role with ansible-galaxy"""
    rolespath = os.path.join(os.getenv('HOME'), '.ansible', 'roles')
    if not os.path.exists(rolespath):
        os.makedirs(rolespath)

    if getattr(roleinstall, '_cache', None) is None:
        # prevent galaxy from crashing if role already installed
        out = subprocess.check_output('ansible-galaxy list', shell=True)
        roleinstall._cache = dict()
        for roleout in out.decode('utf8').split('\n'):
            ma = re.match('- (?P<name>[^,]*), (?P<version>.*)', roleout)
            if not ma:
                continue
            roleinstall._cache[ma.group('name')] = ma.group('version')

    rolename = role.rstrip('/').split('/')[-1]
    if rolename in roleinstall._cache:
        return

    gitmatch = re.match(M, role)

    if os.path.exists(role):
        rolepath = Path(role)
        metapath = rolepath / 'meta' / 'main.yml'

        if os.path.exists(metapath):
            with open(metapath, 'r') as f:
                metadata = yaml.safe_load(f.read())

            if 'role_name' in metadata.get('galaxy_info', {}):
                rolename = metadata['galaxy_info']['role_name']

        target = Path(os.getenv('HOME')) / '.ansible' / 'roles' / rolename

        if target.exists():
            print(f'{target} already in place, not overwriting')
        else:
            print(f'{target} -> {rolepath.resolve()}')
            os.symlink(rolepath.resolve(), target)

    elif '/' in role:
        if not gitmatch:
            host = 'github.com'
            user = 'git'
            path = rolename
        else:
            host = gitmatch.group('host')
            user = gitmatch.group('user') or 'git'
            path = gitmatch.group('path')

        # try an ssh clone, fallback to https which will work if public
        try:
            _galaxyinstall(f'git+ssh://{user}@{host}/{path}')
        except subprocess.CalledProcessError:
            _galaxyinstall(f'git+https://{host}/{path}')
    else:
        _galaxyinstall(role)

    reqpath = os.path.join(
        os.getenv('HOME'),
        '.ansible',
        'roles',
        rolename,
        'requirements.yml',
    )

    if os.path.exists(reqpath):
        reqinstall(reqpath)


def role(role, *hosts, **variables):
    """
    Apply a role.

    This will use the bundled generic role application playbook.
    """
    regexp = '((?P<scheme>[^+]*)\+)?(?P<url>https?([^,]*))(,(?P<ref>.*))?$'  # noqa
    match = re.match(regexp, role)
    if match:
        parts = match.group('url').split('/')
        last = parts[-1] if parts[-1] else parts[-2]
        name = last[:-4] if last.endswith('.git') else last
    else:
        name = role

    if not os.path.exists(role):
        roleinstall(role)
    elif name.startswith('./') or name == '.':
        req = Path(name) / 'requirements.yml'
        if req.exists():
            reqinstall(req)
        name = os.path.join(os.getcwd(), role[1:])

    argv = _argv(*hosts, **variables)

    if os.path.exists(name):
        rolename = name
    else:
        rolename = name.split('/')[-1].split(',')[0]

    argv += ['-e', 'apply_role=' + rolename]
    playbook = os.path.join(os.path.dirname(__file__), 'role-all.yml')
    argv.append(playbook)
    print(' '.join(argv))
    pp = subprocess.Popen(
        argv,
        stderr=sys.stderr,
        stdin=sys.stdin,
        stdout=sys.stdout,
    )
    pp.communicate()
    return pp.returncode


def tasks(tasks, *hosts, **variables):
    """
    Apply a tasks file.

    This will use the bundled generic tasks application playbook.
    """
    if re.match('^https?://', tasks):
        print(cli2.YELLOW, 'Downloading ', cli2.RESET, tasks)
        content = requests.get(tasks).content
        tasks = tasks.split('/')[-1]
        with open(tasks, 'w+') as f:
            f.write(content)
    elif not tasks.startswith('/'):
        tasks = os.path.abspath(tasks)

    argv = _argv(*hosts, **variables)
    argv += ['-e', 'apply_tasks=' + (tasks or ['main'])]
    playbook = os.path.join(os.path.dirname(__file__), 'tasks.yml')
    argv.append(playbook)
    print(' '.join(argv))
    p = subprocess.Popen(
        argv,
        stderr=sys.stderr,
        stdin=sys.stdin,
        stdout=sys.stdout,
    )
    p.communicate()
    return p.returncode


def playbook(playbook, *hosts, **variables):
    """Apply a playbook."""
    if re.match('^https?://', playbook):
        print(cli2.YELLOW, 'Downloading ', cli2.RESET, playbook)
        content = requests.get(playbook).content
        playbook = playbook.split('/')[-1]
        with open(playbook, 'w+') as f:
            f.write(content)

    argv = _argv(*hosts, **variables)
    argv.append(playbook)
    print(' '.join(argv))
    os.environ['ANSIBLE_STDOUT_CALLBACK'] = 'debug'
    p = subprocess.Popen(
        argv,
        stderr=sys.stderr,
        stdin=sys.stdin,
        stdout=sys.stdout,
    )
    p.communicate()
    return p.returncode


def run(source, *hosts_or_tasks, **variables):
    """
    This commands executes a role's tasks with variables from the CLI.

    # this will execute repo/tasks/main.yml
    bigsudo github.com/your/repo @localhost somearg=foo

    # this will execute ref yourbranch's repo/tasks/update.yml
    bigsudo github.com/your/repo,yourbranch @localhost somearg=foo update

    This command requires that the repository contains a meta/main.yml with:

    galaxy_info:
      author: yourname
      description: yourdescription

    Note that you can generate one with the ansible-galaxy init command.
    """
    hosts = []
    tasks = []
    for arg in hosts_or_tasks:
        if '@' in arg:
            hosts.append(arg)
        else:
            tasks.append(arg)

    kwargs = dict(apply_tasks=tasks or ['main'])
    kwargs.update(variables)

    if source.endswith('.yml'):
        return playbook(source, *hosts, **kwargs)
    else:
        return role(source, *hosts, **kwargs)


console_script = cli2.ConsoleScript(
    __doc__,
    default_command='run',
).add_module('bigsudo.console_script')
