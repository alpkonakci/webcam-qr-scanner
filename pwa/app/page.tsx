import { PwaHome } from "./PwaHome";
import { connection } from "next/server";

export default async function Home() {
  // Nonces must be generated per request, never baked into cached HTML.
  await connection();
  return <PwaHome />;
}
