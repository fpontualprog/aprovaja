import { createClient } from "npm:@supabase/supabase-js@2";
import { SignJWT, importPKCS8 } from "npm:jose@5.9.6";

const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey, content-type", "Access-Control-Allow-Methods": "GET, OPTIONS" };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

async function driveToken() {
  const raw = Deno.env.get("GOOGLE_SERVICE_ACCOUNT_JSON");
  if (!raw) throw new Error("Serviço de arquivos não configurado.");
  const sa = JSON.parse(raw);
  const key = await importPKCS8(String(sa.private_key).replace(/\\n/g, "\n"), "RS256");
  const assertion = await new SignJWT({ scope: "https://www.googleapis.com/auth/drive.readonly" }).setProtectedHeader({ alg: "RS256", typ: "JWT" }).setIssuer(sa.client_email).setAudience("https://oauth2.googleapis.com/token").setIssuedAt().setExpirationTime("1h").sign(key);
  const res = await fetch("https://oauth2.googleapis.com/token", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer", assertion }) });
  const data = await res.json();
  if (!res.ok || !data.access_token) throw new Error("Não foi possível autorizar o acesso ao repositório de arquivos.");
  return data.access_token as string;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "GET") return json({ error: "Método não permitido." }, 405);
  try {
    const authorization = req.headers.get("Authorization") || "";
    const token = authorization.toLowerCase().startsWith("bearer ") ? authorization.slice(7).trim() : "";
    if (!token) return json({ error: "Autenticação obrigatória." }, 401);
    const materialId = new URL(req.url).searchParams.get("material_id");
    if (!materialId || !/^[0-9a-f-]{36}$/i.test(materialId)) return json({ error: "Material inválido." }, 400);
    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const anonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const userClient = createClient(supabaseUrl, anonKey, { global: { headers: { Authorization: `Bearer ${token}` } } });
    const { data: { user }, error: userError } = await userClient.auth.getUser(token);
    if (userError || !user) return json({ error: "Sessão inválida ou expirada." }, 401);
    const adminClient = createClient(supabaseUrl, serviceKey);
    const [{ data: profile }, { data: material, error: materialError }] = await Promise.all([
      adminClient.from("profiles").select("role").eq("id", user.id).maybeSingle(),
      adminClient.from("materiais_gratuitos").select("id,titulo,nome_arquivo,tipo_arquivo,drive_file_id,publicado").eq("id", materialId).maybeSingle()
    ]);
    if (materialError) return json({ error: "Não foi possível validar o material." }, 500);
    if (!material) return json({ error: "Material não encontrado." }, 404);
    if (!material.publicado && profile?.role !== "admin") return json({ error: "Este material não está disponível." }, 403);
    const accessToken = await driveToken();
    const driveRes = await fetch(`https://www.googleapis.com/drive/v3/files/${encodeURIComponent(material.drive_file_id)}?alt=media`, { headers: { Authorization: `Bearer ${accessToken}` } });
    if (!driveRes.ok || !driveRes.body) return json({ error: "O arquivo não pôde ser obtido do repositório." }, 502);
    const filename = (material.nome_arquivo || material.titulo || "material").replaceAll("\r", "_").replaceAll("\n", "_").replaceAll('"', "_");
    return new Response(driveRes.body, { status: 200, headers: { ...cors, "Content-Type": driveRes.headers.get("content-type") || "application/octet-stream", "Content-Disposition": `attachment; filename="${filename}"`, "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" } });
  } catch (e) {
    console.error("material-download failure", e);
    return json({ error: e instanceof Error ? e.message : "Erro interno no download." }, 500);
  }
});
