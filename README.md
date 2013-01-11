Openstack-ZFS
=============

zfs plugin for Cinder in openstack Folsom

Based off of work from David Douard in the following blog post. http://www.logilab.org/blogentry/114769

To install copy zol.py to /usr/share/pyshared/cinder/volume and make the following changes to /etc/cinder/cinder.conf

volume\_driver=cinder.volume.zol.ZFSonLinuxISCSIDriver</br>
volume\_group=\<zvol\_path\> </br>
iscsi\_ip\_prefix=\<ip\_prefix\> </br>
iscsi\_ip\_address=\<cinder\_ip\> </br>
san\_thin\_provision=false </br>
san\_ip=\<cinder\_ip\> </br>
san\_zfs\_volume\_base=\<zvol\_path\> </br>
san\_is\_local=true </br>
use\_cow\_images=false
