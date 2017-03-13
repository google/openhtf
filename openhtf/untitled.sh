#!/bin/bash
for i in {1..72}
do
   echo "Step $i"
   ./stage.par "relative 5 position"
done
./stage.par "absolute 0 position"
