.. _archon-changelog:

==========
Change Log
==========

* :bug:`-` Require ``sdss-clu>=0.7.8`` to allow ``archon expose finish --header`` to work with strings that have spaces. It should now be possible to pass commands like ``archon expose finish --header '{"KEYWORD1": [1, "A comment"]}'``. For header keyword values that are a list of value and comment, the list is converted into a tuple internally so that ``astropy`` can parse it correctly.
* :feature:`-` Add option to define additional header keywords in the configuration file that read values from the actor keyword datamodel.

* :release:`0.2.1 <2021-04-06>`
* :bug:`-` Fix Docker creation for tags.

* :release:`0.2.0 <2021-04-06>`
* :support:`-` Basic documentation.
* :feature:`10` Add actor command ``reconnect`` that allows to recreate the TCP/IP connection to one or multiple controllers. If the controller cannot be connected when the actor starts, a warning is issued but the actor will be created.
* :support:`-` Use GitHub Container Registry instead of Docker Hub.
* :feature:`11` Read the Govee H5179 temperature and humidity and write a basic FITS header.
* :feature:`12` Add `.ArchonController` methods to `abort <.ArchonController.abort>`, `read out <.ArchonController.readout>`, and `flush <.ArchonController.flush>` an exposure. Actor ``expose`` command now accepts ``expose start`` and ``expose finish`` to allow for non-blocking integration. Better handling of status flags.

* :release:`0.1.0 <2021-03-06>`
* Initial version of the library and actor. Supports communication with the Archon controller, Archon command tracking and reply parsing, and basic actor functionality, including exposing.
* Build and push docker image to `lvmi/archon <https://hub.docker.com/repository/docker/lvmi/archon>`__.
