"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getAccessToken } from "@/lib/api";

export default function RootPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getAccessToken() ? "/admin/dashboard" : "/login");
  }, [router]);
  return null;
}
