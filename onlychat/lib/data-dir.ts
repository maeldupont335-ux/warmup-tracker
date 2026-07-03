import path from "path";
import fs from "fs";

/**
 * Retourne le répertoire racine des données persistantes.
 * Sur Render : /var/data (disque persistant monté)
 * En local  : {cwd}/data
 */
export function getDataDir(): string {
  const dir = process.env.DATA_DIR ?? path.join(process.cwd(), "data");
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  return dir;
}
