import type { IIncident } from '../types';

export interface KnmPackageDocuments {
  packageId: string;
  documents: { name?: string; downloadUrl: string }[];
}

export function getKnmPackageDocuments(incident: IIncident): KnmPackageDocuments | null {
  const knmPackage = incident.knmPackage;
  const packageId = typeof knmPackage?.packageId === 'string' ? knmPackage.packageId.trim() : '';
  if (
    typeof knmPackage?.status !== 'string' ||
    knmPackage.status.trim().toLowerCase() !== 'generated' ||
    !packageId ||
    !Array.isArray(knmPackage.documents)
  ) {
    return null;
  }

  const documents = knmPackage.documents.flatMap((document) => {
    if (!document || typeof document !== 'object' || typeof document.downloadUrl !== 'string') return [];
    try {
      const url = new URL(document.downloadUrl);
      if (url.protocol !== 'http:' && url.protocol !== 'https:') return [];
      return [{ name: typeof document.name === 'string' ? document.name : undefined, downloadUrl: url.href }];
    } catch {
      return [];
    }
  });

  return documents.length > 0 ? { packageId, documents } : null;
}
