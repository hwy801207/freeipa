# Authors:
#   Rob Crittenden <rcritten@redhat.com>
#   Pavel Zuna <pzuna@redhat.com>
#
# Copyright (C) 2009  Red Hat
# see file 'COPYING' for use and warranty information
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; version 2 only
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
"""
Directory Server Access Control Instructions (ACIs)
"""

from ipalib import api, crud, errors
from ipalib import Object, Command
from ipalib import Flag, Int, List, Str, StrEnum
from ipalib.aci import ACI

_type_map = {
    'user': 'ldap:///uid=*,%s,%s' % (api.env.container_user, api.env.basedn),
    'group': 'ldap:///cn=*,%s,%s' % (api.env.container_group, api.env.basedn),
    'host': 'ldap:///cn=*,%s,%s' % (api.env.container_host, api.env.basedn)
}

_valid_permissions_values = [
    u'read', u'write', u'add', u'delete', u'selfwrite', u'all'
]


def _make_aci(current, aciname, kw):
    try:
        (dn, entry_attrs) = api.Command['taskgroup2_show'](kw['taskgroup'])
    except errors.NotFound:
        # The task group doesn't exist, let's be helpful and add it
        tgkw = {'description': aciname}
        (dn, entry_attrs) = api.Command['taskgroup2_create'](
            kw['taskgroup'], **tgkw
        )

    a = ACI(current)
    a.name = aciname
    a.permissions = kw['permissions']
    a.set_bindrule('groupdn = "ldap:///%s"' % dn)
    if 'attrs' in kw:
        a.set_target_attr(kw['attrs'])
    if 'memberof' in kw:
        (dn, entry_attrs) = api.Command['group2_show'](kw['memberof'])
        a.set_target_filter('memberOf=%s' % dn)
    if 'filter' in kw:
        a.set_target_filter(kw['filter'])
    if 'type' in kw:
        target = _type_map[kw['type']]
        a.set_target(target)
    if 'targetgroup' in kw:
        # Purposely no try here so we'll raise a NotFound
        (dn, entry_attrs) = api.Command['group2_show'](kw['targetgroup'])
        target = 'ldap:///%s' % dn
        a.set_target(target)
    if 'subtree' in kw:
        # See if the subtree is a full URI
        target = kw['subtree']
        if not target.startswith('ldap:///'):
            target = 'ldap:///%s' % target
        a.set_target(target)

    return a

def _convert_strings_to_acis(acistrs):
    acis = []
    for a in acistrs:
        try:
            acis.append(ACI(a))
        except SyntaxError, e:
            # FIXME: need to log syntax errors, ignore for now
            pass
    return acis

def _find_aci_by_name(acis, aciname):
    for a in acis:
        if a.name.lower() == aciname.lower():
            return a
    raise errors.NotFound('ACI with name "%s" not found' % aciname)

def _normalize_permissions(permissions):
    valid_permissions = []
    permissions = permissions.split(',')
    for p in permissions:
        p = p.strip().lower()
        if p in _valid_permissions_values and p not in valid_permissions:
            valid_permissions.append(p)
    return ','.join(valid_permissions)


class aci2(Object):
    """
    ACI object.
    """
    takes_params = (
        Str('aciname',
            cli_name='name',
            doc='name',
            primary_key=True,
        ),
        Str('taskgroup',
            cli_name='taskgroup',
            doc='taskgroup ACI grants access to',
        ),
        List('permissions',
            cli_name='permissions',
            doc='comma-separated list of permissions to grant' \
                '(read, write, add, delete, selfwrite, all)',
            normalizer=_normalize_permissions,
        ),
        List('attrs?',
            cli_name='attrs',
            doc='comma-separated list of attributes',
        ),
        StrEnum('type?',
            cli_name='type',
            doc='type of IPA object (user, group, host)',
            values=(u'user', u'group', u'host'),
        ),
        Str('memberof?',
            cli_name='memberof',
            doc='member of a group',
        ),
        Str('filter?',
            cli_name='filter',
            doc='legal LDAP filter (e.g. ou=Engineering)',
        ),
        Str('subtree?',
            cli_name='subtree',
            doc='subtree to apply ACI to',
        ),
        Str('targetgroup?',
            cli_name='targetgroup',
            doc='group to apply ACI to',
        ),
    )

api.register(aci2)


class aci2_create(crud.Create):
    """
    Create new ACI.
    """
    def execute(self, aciname, **kw):
        """
        Execute the aci-create operation.

        Returns the entry as it will be created in LDAP.

        :param aciname: The name of the ACI being added.
        :param kw: Keyword arguments for the other LDAP attributes.
        """
        assert 'aciname' not in kw
        assert self.api.env.use_ldap2, 'use_ldap2 is False'
        ldap = self.api.Backend.ldap2

        newaci = _make_aci(None, aciname, kw)

        (dn, entry_attrs) = ldap.get_entry(self.api.env.basedn, ['aci'])

        acis = _convert_strings_to_acis(entry_attrs.get('aci', []))
        for a in acis:
            if a.isequal(newaci):
                raise errors.DuplicateEntry()

        newaci_str = str(newaci)
        entry_attrs['acis'].append(newaci_str)

        ldap.update_entry(dn, entry_attrs)

        return newaci_str

    def output_for_cli(self, textui, result, aciname, **options):
        textui.print_name(self.name)
        textui.print_plain(result)
        textui.print_dashed('Created ACI "%s".' % aciname)

api.register(aci2_create)


class aci2_delete(crud.Delete):
    """
    Delete ACI.
    """
    def execute(self, aciname, **kw):
        """
        Execute the aci-delete operation.

        :param aciname: The name of the ACI being added.
        :param kw: unused
        """
        assert 'aciname' not in kw
        assert self.api.env.use_ldap2, 'use_ldap2 is False'
        ldap = self.api.Backend.ldap2

        (dn, entry_attrs) = ldap.get_entry(self.api.env.basedn, ['aci'])

        acistrs = entry_attrs.get('aci', [])
        acis = _convert_strings_to_acis(acistrs)
        aci = _find_aci_by_name(acis, aciname)
        for a in acistrs:
            if aci.isequal(a):
                acistrs.remove(a)
                break

        entry_attrs['aci'] = acistrs

        ldap.update_entry(dn, entry_attrs)

        return True

    def output_for_cli(self, textui, result, aciname, **options):
        """
        Output result of this command to command line interface.
        """
        textui.print_name(self.name)
        textui.print_plain('Deleted ACI "%s".' % aciname)

api.register(aci2_delete)


class aci2_mod(crud.Update):
    """
    Modify ACI.
    """
    def execute(self, aciname, **kw):
        assert self.api.env.use_ldap2, 'use_ldap2 is False'
        ldap = self.api.Backend.ldap2
 
        (dn, entry_attrs) = ldap.get_entry(self.api.env.basedn, ['aci'])

        acis = _convert_strings_to_acis(entry_attrs.get('aci', []))
        aci = _find_aci_by_name(acis, aciname)

        kw.setdefault('aciname', aci.name)
        kw.setdefault('taskgroup', aci.bindrule['expression'])
        kw.setdefault('permissions', aci.permissions)
        kw.setdefault('attrs', aci.target['targetattr']['expression'])
        if 'type' not in kw and 'targetgroup' not in kw and 'subtree' not in kw:
            kw['subtree'] = aci.target['target']['expression']
        if 'memberof' not in kw and 'filter' not in kw:
            kw['filter'] = aci.target['targetfilter']['expression']

        self.api.Command['aci2_delete'](aciname)

        return self.api.Command['aci2_create'](aciname, **kw)

    def output_for_cli(self, textui, result, aciname, **options):
        textui.print_name(self.name)
        textui.print_plain(result)
        textui.print_dashed('Modified ACI "%s".' % aciname)

api.register(aci2_mod)


class aci2_find(crud.Search):
    """
    Search for ACIs.
    """
    def execute(self, term, **kw):
        assert self.api.env.use_ldap2, 'use_ldap2 is False'
        ldap = self.api.Backend.ldap2

        (dn, entry_attrs) = ldap.get_entry(self.api.env.basedn, ['aci'])

        acis = _convert_strings_to_acis(entry_attrs.get('aci', []))
        results = []

        if term:
            term = term.lower()
            for a in acis:
                if a.name.lower().find(term) != -1 and a not in results:
                    results.append(a)
            acis = list(results)
        else:
            results = list(acis)

        if 'aciname' in kw:
            for a in acis:
                if a.name != kw['aciname']:
                    results.remove(a)
            acis = list(results)

        if 'attrs' in kw:
            for a in acis:
                alist1 = sorted(
                    [t.lower() for t in a.target['targetattr']['expression']]
                )
                alist2 = sorted([t.lower() for t in kw['attrs']])
                if alist1 != alist2:
                    results.remove(a)
            acis = list(results)

        if 'taskgroup' in kw:
            try:
                (dn, entry_attrs) = self.api.Command['taskgroup2_show'](
                    kw['taskgroup']
                )
            except errors.NotFound:
                pass
            else:
                for a in acis:
                    if a.bindrule['expression'] != ('ldap:///%s' % dn):
                        results.remove(a)
                acis = list(results)

        if 'permissions' in kw:
            for a in acis:
                alist1 = sorted(a.permissions)
                alist2 = sorted(kw['permissions'])
                if alist1 != alist2:
                    results.remove(a)
                acis = list(results)

        if 'memberof' in kw:
            try:
                (dn, entry_attrs) = self.api.Command['group2_show'](
                    kw['memberof']
                )
            except errors.NotFound:
                pass
            else:
                memberof_filter = '(memberOf=%s)' % dn
                for a in acis:
                    if 'targetfilter' in a.target:
                        filter = a.target['targetfilter']['expression']
                        if filter != memberof_filter:
                            results.remove(a)
                    else:
                        results.remove(a)
                # uncomment next line if you add more search criteria
                # acis = list(results)

        # TODO: searching by: type, filter, subtree

        return [str(aci) for aci in results]

    def output_for_cli(self, textui, result, term, **options):
        textui.print_name(self.name)
        for aci in result:
            textui.print_plain(aci)
            textui.print_plain('')
        textui.print_count(
            len(result), '%i ACI matched.', '%i ACIs matched.'
        )

api.register(aci2_find)


class aci2_show(crud.Retrieve):
    """
    Display ACI.
    """
    def execute(self, aciname, **kw):
        """
        Execute the aci-show operation.

        Returns the entry

        :param uid: The login name of the user to retrieve.
        :param kw: unused
        """
        assert self.api.env.use_ldap2, 'use_ldap2 is False'
        ldap = self.api.Backend.ldap2

        (dn, entry_attrs) = ldap.get_entry(self.api.env.basedn, ['aci'])

        acis = _convert_strings_to_acis(entry_attrs.get('aci', []))

        return str(_find_aci_by_name(acis, aciname))

    def output_for_cli(self, textui, result, aciname, **options):
        textui.print_name(self.name)
        textui.print_plain(result)

api.register(aci2_show)

