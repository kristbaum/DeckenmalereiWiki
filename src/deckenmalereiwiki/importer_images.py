"""
Per-entity image uploading for :class:`MediaWikiImporter`.
"""

from typing import Dict

from .loader import DataLoader


class EntityImageImportMixin:
    """Upload the images belonging to each TEXT entity.

    Mixed into :class:`~deckenmalereiwiki.importer.MediaWikiImporter`, which
    provides the ``self.image_handler`` and ``self.downloads_dir`` attributes
    these methods rely on.
    """

    def _process_entity_images(
        self, loader: DataLoader, entity: Dict, overwrite_existing: bool = False
    ):
        """Upload all images associated with *entity*.

        Without *overwrite_existing*, the images are uploaded straight from the
        local ``downloads/`` folder using the ``{entity_id}.json`` metadata
        sidecars written by ``download-images``; no provider API (e.g. EasyDB)
        is contacted. With *overwrite_existing* ``True``, metadata is rebuilt
        from the loader (which may query a provider API to resolve the source
        link) and the file's ``{{BildMeta}}`` description page is refreshed.
        """
        for name_entity_id, resource in loader.get_entity_image_resources(entity["ID"]):
            if overwrite_existing:
                self._upload_resource_image(loader, name_entity_id, resource)
            else:
                self._upload_sidecar_image(name_entity_id)

    def _upload_sidecar_image(self, name_entity_id: str):
        """Upload one already-downloaded image from its metadata sidecar.

        Reads everything needed from the ``{entity_id}.json`` sidecar so the
        upload never contacts a provider API. Silently skips entities with no
        sidecar (e.g. external-provider images, which are never downloaded) or
        whose recorded file is missing from ``downloads/``.
        """
        meta = self.image_handler.read_sidecar(name_entity_id)
        if not meta or not meta.get("image_file"):
            return
        filepath = self.downloads_dir / meta["image_file"]
        if not filepath.is_file():
            print(f"  Sidecar references missing file: {meta['image_file']}")
            return
        self.image_handler.upload_image(
            filepath,
            meta.get("description", ""),
            meta.get("license", ""),
            rights_holders=meta.get("rights_holders"),
            originators=meta.get("originators"),
            source_url=meta.get("source_url"),
            overwrite_existing=False,
        )

    def _upload_resource_image(
        self, loader: DataLoader, name_entity_id: str, resource: Dict
    ):
        """Download (if needed) and re-upload one image, refreshing its metadata.

        Used by the ``--overwrite-descriptions`` path: metadata is rebuilt from
        the loader and the ``{{BildMeta}}`` description page is rewritten. This
        may query a provider API to resolve the source link.
        """
        fp = self.image_handler.download_image(
            resource["resProvider"], name_entity_id, resource["ID"]
        )
        if not fp:
            return
        resource_id = resource["ID"]
        rights_holders = loader.get_resource_actors(resource_id, "RIGHTS_HOLDERS")
        originators = loader.get_resource_actors(resource_id, "ORIGINATORS")
        source_url = self.image_handler.source_url(resource["resProvider"], resource_id)
        self.image_handler.upload_image(
            fp,
            resource.get("appellation", ""),
            resource.get("resLicense", ""),
            rights_holders=rights_holders,
            originators=originators,
            source_url=source_url,
            overwrite_existing=True,
        )
