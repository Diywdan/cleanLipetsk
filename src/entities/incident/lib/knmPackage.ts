import type { IIncident } from '../types';

export interface KnmPackageDocuments {
  packageId: string;
  documents: { code?: string; name?: string; downloadUrl?: string }[];
}

export function getKnmPackageDocuments(incident: IIncident): KnmPackageDocuments | null {
  const knmPackage = incident.knmPackage;
  const packageId = typeof knmPackage?.packageId === 'string'
    ? knmPackage.packageId.trim()
    : typeof knmPackage?.packageId === 'number' && Number.isSafeInteger(knmPackage.packageId)
      ? String(knmPackage.packageId)
      : '';
  if (
    typeof knmPackage?.status !== 'string' ||
    knmPackage.status.trim().toLowerCase() !== 'generated' ||
    !packageId ||
    !Array.isArray(knmPackage.documents)
  ) {
    return null;
  }

  const documents = knmPackage.documents.flatMap((document) => {
    if (!document || typeof document !== 'object') return [];
    const code = typeof document.code === 'string' ? document.code : undefined;
    const name = typeof document.name === 'string' ? document.name : undefined;
    if (typeof document.downloadUrl !== 'string') {
      return [{ code, name }];
    }
    try {
      const url = new URL(document.downloadUrl);
      if (url.protocol !== 'http:' && url.protocol !== 'https:') return [];
      return [{ code, name, downloadUrl: url.href }];
    } catch {
      return [];
    }
  });

  return documents.length > 0 ? { packageId, documents } : null;
}
