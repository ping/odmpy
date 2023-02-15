# Copyright (C) 2018 github.com/ping
#
# This file is part of odmpy.
#
# odmpy is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# odmpy is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with odmpy.  If not, see <http://www.gnu.org/licenses/>.
#

import sys

from .odm import run, LibbyNotConfiguredError


def main() -> None:  # pragma: no cover
    try:
        run()
    except (KeyboardInterrupt, LibbyNotConfiguredError):
        # we can silently ignore LibbyNotConfiguredError
        # because the message is already shown earlier
        sys.exit(1)


if __name__ == "__main__":
    main()
