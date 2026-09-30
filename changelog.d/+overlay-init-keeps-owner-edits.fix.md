`stayfixed overlay init` no longer records a plugin manifest you had edited as stayfixed's own. It
recorded every manifest it renamed as the bytes it wrote, so an edit made before `init` (a
description of your own, say) read as stayfixed's, and the next `stayfixed overlay upgrade`
refreshed the file: your edit and the account suffix on its name were gone. Such a manifest is still
renamed, and `overlay upgrade` now keeps listing it as hand-edited. `init` also reads every
manifest before it rewrites any, so one that cannot be read stops it with none of them changed.
