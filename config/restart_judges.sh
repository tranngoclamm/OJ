#!/bin/bash

JUDGES=(judge8 judge7 judge6 judge5 judge4 judge3 judge2 judge1)

for j in "${JUDGES[@]}"
do
  docker restart $j
  sleep 5
done
