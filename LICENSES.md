# Licensing Information

This project contains software under two different licenses:

1. Storage Engine Implementations
    - Licensed under GNU General Public License v2.0
    - Located in: src/mysql/videx (MySQL engine) and src/mariadb/videx (MariaDB engine)
    - SPDX-License-Identifier: GPL-2.0

2. Python Implementation
    - Licensed under MIT License
    - Located in: all other codes and scripts outside the engine directories listed above
    - SPDX-License-Identifier: MIT

## Notice
- When using or distributing the MySQL or MariaDB engine components, you must comply with GPL-2.0 terms
- The other components can be used under the more permissive MIT license
- If you combine both components, the resulting work must comply with GPL-2.0
- Files under src/mariadb/videx/mysql-test carry no individual license header. They are part of the
  MariaDB engine tree and are covered by that tree's GPL-2.0 terms.

For full license texts, see the LICENSE directory.
