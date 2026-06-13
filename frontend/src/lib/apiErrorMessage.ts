import { ApiError } from "../api/client";

type QueryRejection = {
  detail?: {
    message?: string;
    suggested_aggregation?: string;
  };
};

export function queryErrorMessage(error: Error | null, fallback: string): string {
  if (!(error instanceof ApiError) || error.status !== 413) return fallback;
  const rejection = error.detail as QueryRejection | undefined;
  const message = rejection?.detail?.message ?? "This query is too large.";
  const suggestion = rejection?.detail?.suggested_aggregation;
  return suggestion ? `${message} Try ${suggestion} aggregation.` : message;
}
