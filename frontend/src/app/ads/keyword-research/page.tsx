"use client";

import { useState } from "react";
import { AppLayout } from "@/components/layout/sidebar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { Search, Loader2, TrendingUp, DollarSign, BarChart3 } from "lucide-react";

export default function KeywordResearchPage() {
  const [seedKeywords, setSeedKeywords] = useState("");
  const [locationId, setLocationId] = useState("2840");
  const [ideas, setIdeas] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  async function doSearch() {
    if (!seedKeywords.trim()) return;
    setLoading(true);
    setSearched(true);
    try {
      const seeds = seedKeywords.split(",").map((s) => s.trim()).filter(Boolean);
      const data = await api.post("/api/ads/keyword-ideas", {
        seed_keywords: seeds,
        location_id: locationId,
        language_id: "1000",
      });
      setIdeas(data.ideas || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  const competitionColor = (c: string) => {
    if (c === "HIGH") return "text-red-600 bg-red-50";
    if (c === "MEDIUM") return "text-yellow-600 bg-yellow-50";
    if (c === "LOW") return "text-green-600 bg-green-50";
    return "text-gray-500 bg-gray-50";
  };

  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Keyword Research</h1>
          <p className="text-muted-foreground">
            Discover new keyword opportunities using Google Keyword Planner
          </p>
        </div>

        {/* Search Form */}
        <Card>
          <CardContent className="p-5">
            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Seed Keywords</label>
                <Input
                  placeholder="e.g. locksmith, key replacement, car lockout"
                  value={seedKeywords}
                  onChange={(e) => setSeedKeywords(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && doSearch()}
                />
                <p className="text-xs text-muted-foreground mt-1">Separate multiple keywords with commas</p>
              </div>
              <div className="flex items-end gap-3">
                <div>
                  <label className="text-sm font-medium mb-1 block">Location</label>
                  <select
                    className="border rounded-md px-3 py-2 text-sm"
                    value={locationId}
                    onChange={(e) => setLocationId(e.target.value)}
                  >
                    <option value="2840">United States</option>
                    <option value="2826">United Kingdom</option>
                    <option value="2124">Canada</option>
                    <option value="2036">Australia</option>
                  </select>
                </div>
                <Button onClick={doSearch} disabled={loading || !seedKeywords.trim()}>
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  ) : (
                    <Search className="w-4 h-4 mr-2" />
                  )}
                  Get Ideas
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Results */}
        {loading ? (
          <Card>
            <CardContent className="p-8 text-center">
              <Loader2 className="w-6 h-6 animate-spin mx-auto mb-2" />
              <p className="text-muted-foreground">Fetching keyword ideas from Google...</p>
            </CardContent>
          </Card>
        ) : ideas.length > 0 ? (
          <>
            {/* Summary */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-1">
                    <BarChart3 className="w-4 h-4 text-blue-500" />
                    <p className="text-xs text-muted-foreground">Ideas Found</p>
                  </div>
                  <p className="text-2xl font-bold">{ideas.length}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-1">
                    <TrendingUp className="w-4 h-4 text-green-500" />
                    <p className="text-xs text-muted-foreground">Avg. Monthly Searches</p>
                  </div>
                  <p className="text-2xl font-bold">
                    {Math.round(ideas.reduce((s, i) => s + (i.avg_monthly_searches || 0), 0) / ideas.length).toLocaleString()}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-1">
                    <DollarSign className="w-4 h-4 text-purple-500" />
                    <p className="text-xs text-muted-foreground">Avg. CPC Range</p>
                  </div>
                  <p className="text-2xl font-bold">
                    ${(ideas.reduce((s, i) => s + (i.low_bid || 0), 0) / ideas.length).toFixed(2)} -
                    ${(ideas.reduce((s, i) => s + (i.high_bid || 0), 0) / ideas.length).toFixed(2)}
                  </p>
                </CardContent>
              </Card>
            </div>

            {/* Table */}
            <Card>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-slate-50">
                        <th className="text-left p-3 font-medium">Keyword</th>
                        <th className="text-right p-3 font-medium">Avg. Monthly Searches</th>
                        <th className="text-center p-3 font-medium">Competition</th>
                        <th className="text-right p-3 font-medium">Low CPC</th>
                        <th className="text-right p-3 font-medium">High CPC</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ideas.map((idea, i) => (
                        <tr key={i} className="border-b hover:bg-slate-50">
                          <td className="p-3 font-medium">{idea.keyword}</td>
                          <td className="p-3 text-right">{(idea.avg_monthly_searches || 0).toLocaleString()}</td>
                          <td className="p-3 text-center">
                            <Badge className={`text-xs ${competitionColor(idea.competition)}`}>
                              {idea.competition}
                            </Badge>
                          </td>
                          <td className="p-3 text-right">${(idea.low_bid || 0).toFixed(2)}</td>
                          <td className="p-3 text-right">${(idea.high_bid || 0).toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </>
        ) : searched ? (
          <Card>
            <CardContent className="p-12 text-center">
              <Search className="w-8 h-8 text-muted-foreground mx-auto mb-3" />
              <p className="text-muted-foreground">No keyword ideas found. Try different seed keywords.</p>
            </CardContent>
          </Card>
        ) : null}
      </div>
    </AppLayout>
  );
}
