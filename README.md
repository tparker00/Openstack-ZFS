Openstack-ZFS
=============

zfs plugin for Cinder in openstack Folsom

Based off of work from David Douard in the following blog post. http://www.logilab.org/blogentry/114769

To install copy zol.py to /usr/share/pyshared/cinder/volume and make the following changes to /etc/cinder/cinder.conf

volume_driver=cinder.volume.zol.ZFSonLinuxISCSIDriver

volume_group=<zvol_path> 

iscsi_ip_prefix=<ip_prefix>

iscsi_ip_address=<cinder_ip>

san_thin_provision=false

san_ip=<cinder_ip>

san_zfs_volume_base=<zvol_path>

san_is_local=true

use_cow_images=false
