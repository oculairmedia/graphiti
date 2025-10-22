import { PostgrestError } from '@supabase/supabase-js';
type Record = {
    browser?: string;
    hostname?: string;
    is_library_metric?: boolean;
    links_count?: number;
    links_have_time?: boolean | null;
    links_raw_columns?: number;
    links_raw_lines?: number | null;
    mode?: string | null;
    nodes_count?: number;
    nodes_have_time?: boolean | null;
    nodes_raw_columns?: number;
    nodes_raw_lines?: number | null;
};
export declare const supabase: import("@supabase/supabase-js").SupabaseClient<any, "public", any>;
export declare function addMetrics(data: Record): Promise<PostgrestError | null>;
export {};
