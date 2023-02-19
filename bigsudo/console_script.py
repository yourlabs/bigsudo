"""Apply a role or playbook without inventory."""

import cli2
import json
from pathlib import Path
import re
import requests
import shlex
import shutil
import subprocess
import sys
import os
import yaml


M = '((?P<user>[^@]*)@)?(?P<host>([a-z0-9_-]+\.[^/]*)+)?/?(?P<path>[^/]+/.*)'  # noqa
os.environ.setdefault('ANSIBLE_STDOUT_CALLBACK', 'unixy')


class ConsoleScript(cli2.Group):
    def __call__(self, *argv):
        if argv and argv[0] not in self:
            argv = ['run'] + list(argv)
        return super().__call__(*argv)
cli = ConsoleScript(doc=__doc__)  # noqa


def _galaxyinstall(*args):
    print('+ ansible-galaxy install ' + ' '.join(args))
    print(
        subprocess.check_output(
            'ansible-galaxy install ' + ' '.join(args),
            shell=True
        ).decode('utf8')
    )


@cli.cmd
def reqinstall(reqpath='requirements.yml', *args):
    """Install requirements recursively."""
    reqpath = str(reqpath)
    _galaxyinstall(*args, '--ignore-errors -r', reqpath)

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


def _argv(hosts, *args, **variables):
    """Return generated ansible args."""
    argv = ['ansible-playbook'] + list(args)

    if '--nosudo' not in args:
        argv += ['--become']

    argv += ['-e', 'ansible_python_interpreter=python3']

    hosts = hosts or ('localhost',)

    user = None
    inv_arg = any([
        a.startswith('--inventory') or a.startswith('-i')
        for a in argv
    ])
    inv = []
    if not inv_arg:
        for host in hosts:
            if '@' in host:
                parts = host.split('@')
                if parts[0]:
                    user = parts[0]
                inv.append(parts[1])
            else:
                inv.append(host)

    ssh_arg = any([a.startswith('--ssh-extra-args') for a in argv])

    if inv == ['localhost']:
        argv += ['-c', 'local']
    elif (inv_arg or len(inv) == 1) and not ssh_arg:
        ssh = {}
        ssh['ControlMaster'] = 'auto'
        ssh['ControlPersist'] = '120s'
        if 'SSHPORT' in os.environ:
            ssh['Port'] = os.getenv('SSHPORT')
        argv += ['--ssh-extra-arg', ' '.join([
            f'-o {key}={value}' for key, value in ssh.items()
        ])]

    if user:
        argv += ['-u', user]

    if inv and not inv_arg:
        argv += ['-i', ','.join(inv) + ',']

    for key, value in variables.items():
        if not isinstance(value, str):
            value = shlex.quote(json.dumps(value))
        # apparently proper proxy quoted values such as foo="'+ bar'"
        elif value.startswith('"'):
            value = "'" + value + "'"
        elif value.startswith("'"):
            value = '"' + value + '"'
        argv += ['-e', key + '=' + value]

    return argv


@cli.cmd
def roleup(role):
    """Remove and reinstall a role"""
    path = os.path.join(os.getenv('HOME'), '.ansible', 'roles', role)
    if os.path.exists(path):
        print('+ rm -rf ' + path)
        shutil.rmtree(path)
    roleinstall(role)


@cli.cmd
def roleinstall(role, *args):
    """Install a role with ansible-galaxy"""
    rolespath = os.path.join(os.getenv('HOME'), '.ansible', 'roles')
    if not os.path.exists(rolespath):
        os.makedirs(rolespath)

    # try to prevent galaxy warning
    default_paths = (
        '/usr/share/ansible/roles',
        '/etc/ansible/roles',
    )
    for path in default_paths:
        if not Path(path).exists():
            try:
                subprocess.call(
                    ['sudo', '-n', 'mkdir', '-p', path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except:  # noqa
                continue

    if getattr(roleinstall, '_cache', None) is None:
        # prevent galaxy from crashing if role already installed
        print('+ ansible-galaxy list')
        out = subprocess.check_output('ansible-galaxy list', shell=True)
        roleinstall._cache = dict()
        for roleout in out.decode('utf8').split('\n'):
            ma = re.match('- (?P<name>[^,]*), (?P<version>.*)', roleout)
            if not ma:
                continue
            roleinstall._cache[ma.group('name')] = ma.group('version')

    rolename = role.rstrip('/').split('/')[-1]
    if rolename in roleinstall._cache and '--force' not in args:
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


@cli.cmd
def role(role, hosts, *args, **variables):
    """
    Apply a role.

    This will use the bundled generic role application playbook.
    """
    if os.path.exists(role):
        role = os.path.abspath(role)
    argv = _argv(hosts, *args, **variables)

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
        rolename = name.split('/')[-1].split(',')[0]
        argv += ['-e', 'apply_role=' + rolename]
    elif os.path.exists(name):
        req = Path(name) / 'requirements.yml'
        if req.exists():
            reqinstall(req)
        argv += ['-e', 'apply_role=' + name]

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
    sys.exit(pp.returncode)


@cli.cmd
def tasks(tasks, hosts: list, *args, **variables):
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

    argv = _argv(hosts, *args, **variables)
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
    sys.exit(p.returncode)


@cli.cmd
def playbook(playbook, hosts: list, *args, **variables):
    """Apply a playbook."""
    if re.match('^https?://', playbook):
        print(cli2.YELLOW, 'Downloading ', cli2.RESET, playbook)
        content = requests.get(playbook).content
        playbook = playbook.split('/')[-1]
        with open(playbook, 'w+') as f:
            f.write(content)

    argv = _argv(hosts, *args, **variables)
    argv.append(playbook)
    print(' '.join(argv))

    p = subprocess.Popen(
        argv,
        stderr=sys.stderr,
        stdin=sys.stdin,
        stdout=sys.stdout,
    )
    p.communicate()
    sys.exit(p.returncode)


@cli.cmd
def run(source, *hosts_or_tasks_or_args, **variables):
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
    args = []
    ansible_started = False

    for arg in hosts_or_tasks_or_args:
        if arg.startswith('-'):
            ansible_started = True
        if ansible_started:
            args.append(arg)
        elif '@' in arg and ' ' not in arg:
            hosts.append(arg)
        else:
            tasks.append(arg)

    if source.endswith('.yml'):
        return playbook(source, hosts, *args, **variables)
    else:
        variables['apply_tasks'] = tasks or ['main']
        return role(source, hosts, *args, **variables)
