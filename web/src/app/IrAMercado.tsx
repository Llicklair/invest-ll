"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export function IrAMercado() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/mercado/");
  }, [router]);
  return (
    <p className="text-sm text-tinta-2">
      Abriendo <Link href="/mercado/" className="text-acento underline">Mercado</Link>…
    </p>
  );
}
