import path from "path";
import fs from "fs";

/**
 * Répertoire racine des données persistantes (historique + config), en local: {cwd}/data.
 */
export function getDataDir(): string {
  const dir = process.env.DATA_DIR ?? path.join(process.cwd(), "data");
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  return dir;
}
