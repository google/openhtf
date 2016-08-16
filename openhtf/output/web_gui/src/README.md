# OpenHTF Web GUI Client

OpenHTF's web GUI client is an [Angular2](https://angular.io/) app written in
[TypeScript](https://www.typescriptlang.org/). It is designed to be served by
the `openhtf.output.web_gui` (runnable) Python module.

Building with `npm build` will populate the `dist` directory with all the
artifacts that need to be served in order to host the app. The
`openhtf.output.web_gui` module will serve the built app from `dist` if
available, or from `../prebuilt` otherwise. The `../prebuilt` directory can be
updated (with the contents of `dist/`) by doing `npm run update_prebuilt`.

The web GUI client's main entry point is `app/main.ts`, and the app is set up
to be loaded into the `<app>` element in `app/index.html`.

# How to write a Plugin! 

It is a truth universally acknowledged that an application with infinite 
use cases must be in want of a plugin interface. Here's how to write one!

## Contents

A basic, bare-bones plugin package structure looks like this: 
```
/example_plugin
	|
	-- setup.py
	|
	-- /example_plugin
			|
			-- __init__.py
			|
			-- /plugin
				|
				-- main.ts
				|
				-- example_plugin.html
				|
				-- example_service.ts
```

A plugin with this structure would be able to show up in the frontend and 
make calls to the backend Tornado server to request information.

### Backend Structure

Everything adding to the backend goes in the __init__.py module! It requires 
two main parts: 

#### Tornado Handler and Handlers Variable

If you need to pull information from the backend, then you need to create a 
Tornado Handler to service it. Some required functions: 
- get() - Will return data requested when URL is called. Can take 
arguments that refer to capture groups specified in the regex URL section 
of the handlers variable. 
- initialize() - Will initialize any variables you request from the backend. 
Must contain the following arguments: station_store, host, port, path. 

The handlers variable list is what OpenHTF will use to configure and add your 
tornado handler. A simple example: 
```
handlers=[(r'/example/', ExampleHandler),
		 (r'/example2/', ExampleHandler2)]
```
The list consists tuples containing the regex for the URL you need served, 
and the name of the handler to serve it to.

#### Configs Variable 

This dictionary specifies your configurations for the frontend portions of 
the plugin. Make sure these variables match the class and tag you use in your 
main.ts module; this component will populate the body of your plugin tab.
Another example: 
```
configs={
	'class':'ExamplePlugin',
	'tag':'example-plugin', 
	'label':'example', 
	'icon':'pets'}
```
- label: The label for the tab for your plugin
- icon: Optional, but refers to the icon from Material Icons that you want
on your tab. (replace any spaces with underscores)

### Frontend Structure

All frontend assets MUST be in a folder labeled 'plugin' in order to be built
into OpenHTF. In this folder, your main angular component class MUST be in 
a module called main.ts. The class and tag in the main.ts must match the class 
and tag fields in the config variable. This class must also take the following
inputs in order to be built correctly; whether they are used is up to you:
- currentMillis: number; 
- stationInfo: any;
- currentMillisJob: number;
- tests: any[];

#### SOME NOTES FOR FRONTEND ASSETS

- For references to styleUrls and templateUrl in the Component wrapper, use the 
url 'plugin/(NAME OF PACKAGE)/(NAME OF FILE)', 
i.e, '/plugin/example_plugin/example_plugin.html'
- For imports of html or css scripts, use urls relative to the plugin folder 
in your package

## Building the Plugin

Once the contents are finished, it needs to be added to OpenHTF and then built 
before it can be used. Note: If you are using a virtualenv, this requires npm 
version 3.10.6 or higher. 

1. Install your package.
2. On command line (unix): 
```
cd openhtf/openhtf/output/web_gui/src/
npm run update_plugins (NAME(S) OF PLUGIN(S))  
		/i.e., npm run update_plugins example_plugin
npm run build
```

To run the frontend server, you also need to hook up the back end of the 
plugin. To do this, navigate to the top level openhtf folder and type 
'python -m openhtf.output.web_gui --plugins (NAME(S) OF PLUGIN(S)'
For example: `python -m openhtf.output.web_gui --plugins example_plugin' 

And it should work! Some things to note: 
- Making changes to the frontend of your plugin package requires the plugin 
to be rebuilt. In order to do this, **stop the server**, and then repeat the 
above steps. Things may not update correctly if you don't stop the server first. 
- Changes to the backend portion of your plugin requires reinstalling the package.
- Running Openhtf **without** plugins after using a plugin also requires it to 
be built again. Stop the server, and repeat the steps above using these steps 
instead: 
```
npm run update_plugins
npm run build 
   ... 
python -m openhtf.output.web_gui
```

