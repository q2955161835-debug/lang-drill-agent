import { apiDelete, apiPost, apiPostFile } from "../../api";
import type {
  ResourceImportMetadata,
  ResourceImportRecord,
  ResourceImportTarget,
} from "./types";

export type ResourceImportApi = {
  stage(target: ResourceImportTarget, file: File): Promise<ResourceImportRecord>;
  parse(id: string, metadata: ResourceImportMetadata): Promise<ResourceImportRecord>;
  confirm(id: string, metadata: ResourceImportMetadata): Promise<unknown>;
  cancel(id: string): Promise<void>;
};

export const resourceImportApi: ResourceImportApi = {
  stage(target, file) {
    const params = new URLSearchParams({ target, filename: file.name });
    return apiPostFile<{ item: ResourceImportRecord }>(
      `/api/resource-imports/stage?${params.toString()}`,
      file,
    ).then((response) => response.item);
  },
  parse(id, metadata) {
    return apiPost<{ item: ResourceImportRecord }>(
      `/api/resource-imports/${encodeURIComponent(id)}/parse`,
      metadata,
    ).then((response) => response.item);
  },
  confirm(id, metadata) {
    return apiPost(
      `/api/resource-imports/${encodeURIComponent(id)}/confirm`,
      { ...metadata, confirmed: true },
    );
  },
  cancel(id) {
    return apiDelete(`/api/resource-imports/${encodeURIComponent(id)}`).then(() => undefined);
  },
};
