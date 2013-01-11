# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# Copyright 2011 Justin Santa Barbara
# Copyright 2012 David DOUARD, LOGILAB S.A.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""
Driver for ZFS-on-Linux-stored volumes.

This is mainly taken from  http://www.logilab.org/blogentry/114769 with
modifications to make it work well with cinder and OpenStack Folsom.

My setup is utilizing locally stored ZFS volumes so SSH access was not tested
"""

import os

from cinder import exception
from cinder import flags
from cinder import utils
from cinder.openstack.common import cfg
from cinder.openstack.common import log as logging
from cinder.volume import iscsi
from cinder.volume.driver import _iscsi_location
from cinder.volume.san import SanISCSIDriver


LOG = logging.getLogger(__name__)

san_opts = [
    cfg.StrOpt('san_zfs_command',
               default='zfs',
               help='The ZFS command.'),
    ]

FLAGS = flags.FLAGS
FLAGS.register_opts(san_opts)


class ZFSonLinuxISCSIDriver(SanISCSIDriver):
    """Executes commands relating to ZFS-on-Linux-hosted ISCSI volumes.

    Basic setup for a ZoL iSCSI server:

    XXX

    Note that current implementation of ZFS on Linux does not handle:

      zfs allow/unallow

    For now, needs to have root access to the ZFS host. The best is to
    use a ssh key with ssh authorized_keys restriction mechanisms to
    limit root access.

    Make sure you can login using san_login & san_password/san_private_key
    """
    ZFSCMD = FLAGS.san_zfs_command

    _local_execute = utils.execute

    def _getrl(self):
        return self._runlocal
    def _setrl(self, v):
        if isinstance(v, basestring):
            v = v.lower() in ('true', 't', '1', 'y', 'yes')
        self._runlocal = v
    run_local = property(_getrl, _setrl)

    def __init__(self):
        super(ZFSonLinuxISCSIDriver, self).__init__()
        self.tgtadm.set_execute(self._execute)
        self.tgtadm = iscsi.get_target_admin()
        LOG.info("run local = %s (%s)" % (self.run_local, FLAGS.san_is_local))

    def set_execute(self, execute):
        LOG.debug("override local execute cmd with %s (%s)" % (
            repr(execute), execute.__module__))
        self._local_execute = execute

    def _execute(self, *cmd, **kwargs):
        if self.run_local:
            LOG.debug("LOCAL execute cmd %s (%s)" % (cmd, kwargs))
            return self._local_execute(*cmd, **kwargs)
        else:
            LOG.debug("SSH execute cmd %s (%s)" % (cmd, kwargs))
            check_exit_code = kwargs.pop('check_exit_code', None)
            command = ' '.join(cmd)
            return self._run_ssh(command, check_exit_code)

    def _create_volume(self, volume_name, sizestr):
        zfs_poolname = self._build_zfs_poolname(volume_name)

        # Create a zfs volume
        cmd = [self.ZFSCMD, 'create']
        if FLAGS.san_thin_provision:
            cmd.append('-s')
        cmd.extend(['-V', sizestr])
        cmd.append(zfs_poolname)
        self._execute(*cmd, run_as_root=True)

    def _volume_not_present(self, volume_name):
        zfs_poolname = self._build_zfs_poolname(volume_name)
        try:
            out, err = self._execute(self.ZFSCMD, 'list', '-H', 
                                     zfs_poolname, run_as_root=True)
            if out.startswith(zfs_poolname):
                return False
        except Exception as e:
            # If the volume isn't present
            return True
        return False

    def create_volume_from_snapshot(self, volume, snapshot):
        """Creates a volume from a snapshot."""
        zfs_snap = self._build_zfs_poolname(snapshot['name'])
        zfs_vol = self._build_zfs_poolname(snapshot['name'])
        self._execute(self.ZFSCMD, 'clone', zfs_snap,
                      zfs_vol, run_as_root=True)
        self._execute(self.ZFSCMD, 'promote', zfs_vol, run_as_root=True)

    def delete_volume(self, volume):
        """Deletes a volume."""
        if self._volume_not_present(volume['name']):
            # If the volume isn't present, then don't attempt to delete
            return True
        zfs_poolname = self._build_zfs_poolname(volume['name'])
        self._execute(self.ZFSCMD, 'destroy', zfs_poolname, run_as_root=True)

    def create_export(self, context, volume):
        """Creates an export for a logical volume."""
        iscsi_name = "%s%s" % (FLAGS.iscsi_target_prefix, volume['name'])
        # set volume path properly for ZFS
        volume_path = "/dev/zvol/%s/%s" % (FLAGS.volume_group, volume['name'])
        model_update = {}

        # TODO(jdg): In the future move all of the dependent stuff into the
        # cooresponding target admin class
        if not isinstance(self.tgtadm, iscsi.TgtAdm):
            lun = 0
            self._ensure_iscsi_targets(context, volume['host'])
            iscsi_target = self.db.volume_allocate_iscsi_target(context,
                                                                volume['id'],
                                                                volume['host'])
        else:
            lun = 1
            iscsi_target = 0

        # NOTE(jdg): For TgtAdm case iscsi_name is the ONLY param we need
        # should clean this all up at some point in the future
        tid = self.tgtadm.create_iscsi_target(iscsi_name,
                                              iscsi_target,
                                              0,
                                              volume_path)
        model_update['provider_location'] = _iscsi_location(
            FLAGS.iscsi_ip_address, tid, iscsi_name, lun)
        return model_update

    def remove_export(self, context, volume):
        """Removes an export for a logical volume."""
        # NOTE(jdg): tgtadm doesn't use the iscsi_targets table
        # TODO(jdg): In the future move all of the dependent stuff into the
        # cooresponding target admin class
        if not isinstance(self.tgtadm, iscsi.TgtAdm):
            try:
                iscsi_target = self.db.volume_get_iscsi_target_num(context,
                                                               volume['id'])
            except exception.NotFound:
                LOG.info(_("Skipping remove_export. No iscsi_target "
                           "provisioned for volume: %s"), volume['id'])
                return
        else:
            iscsi_target = 0

        try:

            # NOTE: provider_location may be unset if the volume hasn't
            # been exported
            location = volume['provider_location'].split(' ')
            iqn = location[1]

            # ietadm show will exit with an error
            # this export has already been removed
            self.tgtadm.show_target(iscsi_target, iqn=iqn)

        except Exception as e:
            LOG.info(_("Skipping remove_export. No iscsi_target "
                       "is presently exported for volume: %s"), volume['id'])
            return

        self.tgtadm.remove_iscsi_target(iscsi_target, 0, volume['id'])

    def check_for_export(self, context, volume_id):
        """Make sure volume is exported."""
        vol_uuid_file = 'volume-%s' % volume_id
        volume_path = os.path.join(FLAGS.volumes_dir, vol_uuid_file)
        if os.path.isfile(volume_path):
            iqn = '%s%s' % (FLAGS.iscsi_target_prefix,
                            vol_uuid_file)
        else:
            raise exception.PersistentVolumeFileNotFound(volume_id=volume_id)

        # TODO(jdg): In the future move all of the dependent stuff into the
        # cooresponding target admin class
        if not isinstance(self.tgtadm, iscsi.TgtAdm):
            tid = self.db.volume_get_iscsi_target_num(context, volume_id)
        else:
            tid = 0

        try:
            self.tgtadm.show_target(tid, iqn=iqn)
        except exception.ProcessExecutionError, e:
            # Instances remount read-only in this case.
            # /etc/init.d/iscsitarget restart and rebooting cinder-volume
            # is better since ensure_export() works at boot time.
            LOG.error(_("Cannot confirm exported volume "
                        "id:%(volume_id)s.") % locals())
            raise

    def local_path(self, volume):
        zfs_poolname = self._build_zfs_poolname(volume['name'])
        zvoldev = '/dev/zvol/%s' % zfs_poolname
        return zvoldev

    def _build_zfs_poolname(self, volume_name):
        zfs_poolname = '%s%s' % (FLAGS.san_zfs_volume_base, volume_name)
        return zfs_poolname
