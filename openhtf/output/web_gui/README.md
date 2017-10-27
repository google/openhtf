# OpenHTF web GUI client

## Development

Start the dashboard server on the default port by running the following from
the project root directory:

```
python -m openhtf.output.servers.dashboard_server --no-launch-web-gui
```

Start the Webpack watcher by running the following from the
`openhtf/output/web_gui` directory in another tab:

```
npm install
npm run start
```

You can then visit the app at http://localhost:8080/. The app should connect to
the dashboard server and should reload automatically when changes are made.
You can then run OpenHTF tests separately and they should be picked up by the
dashboard server and appear on the web page.
