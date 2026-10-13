import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

/** Shown when NEXT_PUBLIC_SUPABASE_* env vars are missing, instead of a broken sign-in. */
export function SetupNotice() {
  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Supabase isn&apos;t configured yet</CardTitle>
        <CardDescription>
          Add <code className="font-mono">NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
          <code className="font-mono">NEXT_PUBLIC_SUPABASE_ANON_KEY</code> to the root{" "}
          <code className="font-mono">.env</code>, then restart <code className="font-mono">make dev</code>.
        </CardDescription>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        See <code className="font-mono">docs/PROGRESS.md</code> → “Supabase setup”.
      </CardContent>
    </Card>
  );
}
