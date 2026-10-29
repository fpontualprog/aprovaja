import { createClient } from "npm:@supabase/supabase-js@2";
import { SignJWT, importPKCS8 } from "npm:jose@5.9.6";

const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type", "Access-Control-Allow-Methods": "POST, OPTIONS" };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });
async function driveToken() {
  const raw = Deno.env.get("GOOGLE_SERVICE_ACCOUNT_JSON");
  if (!raw) throw new Error("Serviço de arquivos não configurado.");
  const sa = JSON.parse(raw);
  const key = await importPKCS8(String(sa.private_key).replace(/\\n/g, "\n"), "RS256");
  const assertion = await new SignJWT({ scope: "https://www.googleapis.com/auth/drive.readonly" }).setProtectedHeader({ alg: "RS256", typ: "JWT" }).setIssuer(sa.client_email).setAudience("https://oauth2.googleapis.com/token").setIssuedAt().setExpirationTime("1h").sign(key);
  const res = await fetch("https://oauth2.googleapis.com/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion }) });
  const data = await res.json();
  if (!res.ok || !data.access_token) throw new Error("Não foi possível autorizar o acesso ao Drive.");
  return data.access_token as string;
}
Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "Método não permitido." }, 405);
  try {
    const token = (req.headers.get("Authorization") || "").replace(/^Bearer\\s+/i, "");
    if (!token) return json({ error: "Autenticação obrigatória." }, 401);
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const userClient = createClient(supabaseUrl, anonKey, { global: { headers: { Authorization: `Bearer ${token}` } } });
    const { data: { user }, error: userError } = await userClient.auth.getUser(token);
    if (userError || !user) return json({ error: "Sessão inválida ou expirada." }, 401);
    const adminClient = createClient(supabaseUrl, serviceKey);
    const { data: profile } = await adminClient.from("profiles").select("role").eq("id", user.id).maybeSingle();
    if (profile?.role !== "admin") return json({ error: "Apenas administradores podem sincronizar o Drive." }, 403);
    const folderId = Deno.env.get("GOOGLE_DRIVE_FOLDER_ID");
    if (!folderId) return json({ error: "Pasta do Drive não configurada no servidor." }, 500);
    const accessToken = await driveToken();
    let pageToken: string | undefined;
    const files: Array<{id:string;name:string;mimeType:string;modifiedTime?:string;size?:string}> = [];
    do {
      const params = new URLSearchParams({ q: `'${folderId.replace(/'/g, "\\'")}' in parents and trashed = false`, fields: "nextPageToken,files(id,name,mimeType,modifiedTime,size)", pageSize: "100", orderBy: "name" });
      if (pageToken) params.set("pageToken", pageToken);
      const response = await fetch(`https://www.googleapis.com/drive/v3/files?${params}`, { headers: { Authorization: `Bearer ${accessToken}` } });
      const data = await response.json();
      if (!response.ok) return json({ error: "Não foi possível listar a pasta do Drive." }, 502);
      files.push(...(data.files || [])); pageToken = data.nextPageToken;
    } while (pageToken && files.length < 1000);
    if (!files.length) return json({ ok: true, encontrados: 0, importados: 0, ignorados: 0, mensagem: "Nenhum arquivo encontrado na pasta configurada." });
    const ids = files.map(f => f.id).filter(Boolean);
    if (!ids.length) return json({ ok: true, encontrados: 0, importados: 0, ignorados: 0, mensagem: "Nenhum arquivo encontrado na pasta configurada." });
    const { data: existing, error: existingError } = await adminClient.from("materiais_gratuitos").select("drive_file_id").in("drive_file_id", ids);
    if (existingError) return json({ error: "Não foi possível verificar os materiais já cadastrados." }, 500);
    const known = new Set((existing || []).map(x => x.drive_file_id));
    const newFiles = files.filter(f => f.id && !known.has(f.id));
    const rows = newFiles.map(f => {
      const ext = (f.name.split(".").pop() || "pdf").toUpperCase();
      return { titulo: f.name.replace(/\\.[^.]+$/, ""), disciplina: "A classificar", categoria: "Outro", tipo_arquivo: ext, drive_file_id: f.id, nome_arquivo: f.name, drive_modified_time: f.modifiedTime || null, publicado: false, criado_por: user.id };
    });
    if (rows.length) {
      const { error: insertError } = await adminClient.from("materiais_gratuitos").insert(rows);
      if (insertError) return json({ error: "Arquivos encontrados, mas não foi possível criar os rascunhos no catálogo." }, 500);
    }
    return json({ ok: true, encontrados: files.length, importados: rows.length, ignorados: files.length - rows.length, mensagem: "Os arquivos foram importados como rascunhos. Revise disciplina e conteúdos antes de publicar." });
  } catch (e) {
    console.error("sync-drive-materials failure", e);
    return json({ error: e instanceof Error ? e.message : "Erro interno na sincronização." }, 500);
  }
});
