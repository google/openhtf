#!/bin/bash
trap "kill 0" SIGINT
(npm run watch:css) &
(npm run watch:js) &
(npm run watch:html) &
(npm run watch:proto) &
wait
