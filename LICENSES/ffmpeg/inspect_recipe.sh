#!/bin/bash
# Read-only metadata evaluation of the fixed upstream recipe checkout.
# No download/build functions or their printed commands are executed.
set -e
cd "$1"
script="$2"
source util/vars.sh win64 gpl 8.1
source util/dl_functions.sh
SELF="$script"
STAGENAME="$(basename "$script" .sh)"
source "$script"
if ffbuild_enabled; then
    printf 'ENABLED\n'
    printf 'DEPENDENCIES\n'
    ffbuild_depends
    printf 'DOWNLOAD\n'
    command="$(ffbuild_dockerdl)"
    printf '%s\n' "$command"
    printf 'CONFIGURE\n'
    ffbuild_configure
else
    printf 'DISABLED\n'
fi
