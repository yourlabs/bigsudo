"""Apply a role or playbook without inventory."""

import cli2
import re
import shlex
import subprocess
import sys
import os


def _argv(*hosts, **variables):
    """Return generated ansible args."""

    if ('v' in console_script.parser.dashargs
        or 'vv' in console_script.parser.dashargs):
        os.environ['ANSIBLE_STDOUT_CALLBACK'] = 'debug'

    argv = ['ansible-playbook'] + [
        arg
        for arg in console_script.parser.argv_all
        if arg.startswith('-')
    ]

    if not hosts:
        hosts = ('localhost',)

    if hosts == ('localhost',):
        argv += ['-c', 'local']

    if hosts:
        argv += ['-i', ','.join(hosts) + ',']

    for key, value in variables.items():
        argv += ['-e', key + '=' + shlex.quote(value)]

    return argv


def role(role, *hosts, **variables):
    """
    Apply a role.

    This will use the bundled generic role application playbook.
    """
    regexp = '((?P<scheme>[^+]*)\+)?(?P<url>https?([^,]*))(,(?P<ref>.*))?$'
    match = re.match(regexp, role)
    if match:
        parts = match.group('url').split('/')
        last = parts[-1] if parts[-1] else parts[-2]
        name = last[:-4] if last.endswith('.git') else last
    else:
        name = role

    if not os.path.exists(role):
        out = subprocess.check_output([
            'ansible-galaxy', 'list', name
        ])
        if b'not found' in out:
            print(subprocess.check_output([
                'ansible-galaxy', 'install', role
            ]))
    elif name.startswith('./') or name == '.':
        name = os.path.join(os.getcwd(), role[1:])

    taskfile = console_script.parser.options.get('taskfile', 'main')
    argv = _argv(*hosts, **variables)
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
    return pp.returncode


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
    p = subprocess.Popen(
        argv,
        stderr=sys.stderr,
        stdin=sys.stdin,
        stdout=sys.stdout,
    )
    p.communicate()
    return p.returncode

console_script = cli2.ConsoleScript(
    __doc__,
).add_module('ansible_apply.console_script')
