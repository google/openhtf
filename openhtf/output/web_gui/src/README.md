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
