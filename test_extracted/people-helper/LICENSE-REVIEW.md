# License Review Required

This package was extracted from [`Ehsas317/people-helper`](https://github.com/Ehsas317/people-helper).

You MUST determine the correct license before publishing. The original source
file's copyright headers have been preserved (required by most licenses). A copy
of the source repo's LICENSE file (if it existed) is in `SOURCE-LICENSE` for
reference.

## Scenarios

1. **If the source is MIT/Apache-2.0/BSD/ISC (permissive):**
   - You may assign any license to your extraction, including MIT.
   - You MUST preserve the original copyright notice in the source files.
   - For Apache 2.0: also include the original NOTICE file if one exists.
   - Create a LICENSE file with your chosen license text.
   - Update the manifest's license field (e.g., `license = "MIT"` in pyproject.toml).

2. **If the source is GPL/LGPL/AGPL (copyleft):**
   - The extracted package MUST use the SAME copyleft license.
   - Copy the source's LICENSE file as your LICENSE.
   - Update the manifest's license field accordingly.
   - Note: LGPL-3.0 allows the extracted code to remain LGPL while being
     linked into a non-LGPL application; GPL/AGPL does not.

3. **If the source has NO license file:**
   - Under default copyright law, all code is "all rights reserved."
   - Extracting and republishing this code may be a copyright violation.
   - Obtain explicit permission from the copyright holder before publishing.
   - If you have permission, create a LICENSE file documenting the grant.

4. **If the source is BSD-2/3-Clause or ISC:**
   - Compatible with MIT. Preserve the original copyright notice and the
     BSD/ISC license text in your extracted package's LICENSE file.

5. **If the source is MPL-2.0 (file-level copyleft):**
   - MPL-licensed files must remain MPL-2.0 — you cannot relicense them.
   - Apply MPL-2.0 to your extracted package, or remove the MPL-licensed portions.

## Once you have determined the correct license

1. Create a LICENSE file with the chosen license text.
2. Update the manifest's `license` field (e.g., uncomment in pyproject.toml).
3. Delete this LICENSE-REVIEW.md file.
4. Delete SOURCE-LICENSE if you've created your own LICENSE.

## Attribution

This package was extracted from [`Ehsas317/people-helper`](https://github.com/Ehsas317/people-helper).
Original code is under that repo's license; this extraction's license is
determined by you per the scenarios above.
