# README #

Source code for the project [NeutMon](http://vecchio.iet.unipi.it/neutmon/).

EU-wide rules concerning net neutrality are one of the major achievements towards the Digital Single Market. According to these rules, blocking, throttling, and discrimination of traffic by Internet Service Providers (ISPs) is not allowed. All traffic has to be treated equally, and no form of traffic prioritization can be enforced (with few exceptions: preserving the integrity of the network, managing temporary congestions, and compliance with legal obligations). So far, research on net neutrality focused on the wired part of the Internet. However, in recent years, smartphones and tablets have become the preferred choice for accessing a large number of networked services and applications, from social networks to video streaming. NeutMon is aimed at studying net neutrality in a mobile broadband context. NeutMon collects networks metrics related to net neutrality while producing traffic belonging to different classes. Also the path experienced by the different classes of traffic is collected, to possibly discover traffic differentiation in terms of forwarding strategies.

NeutMon is financed in the context of the Horizon 2020 [MONROE](http://www.monroe-project.eu/) project, Measuring Mobile Broadband Networks in Europe (research and innovation programme under grant agreement No 644399).

## Requirements ##

Python 2.7

## Install ##

	$ git clone https://github.com/NeutMon/neutmon.git
	
## Configuration ##

In `neutmon/handlers.py` change the value of the variable `DEFAULT_SERVER_ADDRESS`
with the name or IP address of your server machine.

## Run test ##

Needs root.

On server:

	$ ./server.py

On client:

	$ ./client.py

Use option `-h` or `--help` with client or server to obtain more options.
