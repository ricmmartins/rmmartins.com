# Unlisted PDF pages

`/nvis/` and `/nvidia/` use `layouts/_default/resume.html`. GitHub Pages
redirects the extensionless `/nvis` URL to `/nvis/`.

Store PDFs under `assets/documents/`, not `static/`. Set `params.pdfAsset`
and `params.pdfDownloadName` in the page front matter to choose the embedded
asset and download filename. The default asset and filename preserve the
existing `/nvidia/` page.

The template embeds the PDF in HTML and creates a browser-local Blob URL for
viewing and downloading. It does not publish a separate PDF URL, because
GitHub Pages does not support custom `X-Robots-Tag` response headers for PDFs.
The HTML carries `noindex, nofollow, noarchive, nosnippet, noimageindex`.

Keep `build.list: never`, `sitemap.disable: true`, and HTML-only outputs.
Do not add links from menus, posts, or other public pages. Do not disallow
these pages in `robots.txt`: search crawlers must fetch the HTML to see
`noindex`.

This is not authentication or confidentiality. Anyone with the URL can open,
download, and redistribute the PDF. The source PDFs are also accessible in
this public GitHub repository; the site's directives do not govern GitHub
URLs or third-party copies.

After a production Hugo build, run `python scripts/check_unlisted_documents.py`
to check the embedded bytes, indexing directives, and exclusion from generated
discovery surfaces.
