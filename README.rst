ansible-apply: apply remote tasks, supports command line inventory
==================================================================

Ansible-apply takes the tasks file spec as first argument::

   ansible-apply role.name
   ansible-apply role.name/some_tasks
   ansible-apply https://some/playbook.yml
   ansible-apply ./playbook.yml

It will automatically download the playbook or role if not found.

Then, the command takes any number of hosts and inventory variables on
the command line::

   ansible-apply role.name server1 server2 update=true

Finnaly, any argument passed with dashes are forwarded to the
ansible-playbook command it generates, but named args must use the ``=``
notation, and not a space to not confuse the command line parser::

   # works:
   ansible-apply role.name server2 update=true --become-user=root
   # does not:
   ansible-apply role.name server2 update=true --become-user root
