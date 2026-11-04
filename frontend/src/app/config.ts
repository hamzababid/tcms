/** Build-time configuration. The product name matches the backend's TCMS_PRODUCT_NAME. */
export const PRODUCT_NAME: string = (import.meta.env.VITE_PRODUCT_NAME as string | undefined) ?? "Assay";
