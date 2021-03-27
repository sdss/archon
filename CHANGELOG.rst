.. _archon-changelog:

==========
Change Log
==========

* :support:`-` Basic documentation.
* :feature:`10` Add actor command ``reconnect`` that allows to recreate the TCP/IP connection to one or multiple controllers. If the controller cannot be connected when the actor starts, a warning is issued but the actor will be created.
* :support:`-` Use GitHub Container Registry instead of Docker Hub.
* :feature:`11` Read the Govee H5179 temperature and humidity and write a basic FITS header.

* :release:`0.1.0 <2021-03-06>`
* Initial version of the library and actor. Supports communication with the Archon controller, Archon command tracking and reply parsing, and basic actor functionality, including exposing.
* Build and push docker image to `lvmi/archon <https://hub.docker.com/repository/docker/lvmi/archon>`__.
