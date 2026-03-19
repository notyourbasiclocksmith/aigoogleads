"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { AppLayout } from "@/components/layout/sidebar";
import {
  MapPin, Star, FileText, Image, Plus, Sparkles, Send,
  Loader2, AlertCircle, MessageSquare, ThumbsUp, Eye,
  MousePointerClick, Calendar, Trash2, Clock, ChevronDown,
  RefreshCw, ExternalLink, X,
} from "lucide-react";

type Tab = "posts" | "reviews" | "images";

interface GBPPost {
  id: string;
  location_id: string;
  post_type: string;
  summary: string;
  status: string;
  auto_generated: boolean;
  scheduled_for: string | null;
  published_at: string | null;
  views: number;
  clicks: number;
  created_at: string;
}

interface GBPReview {
  id: string;
  reviewer_name: string;
  rating: number;
  comment: string;
  review_time: string;
  reply_text: string | null;
  ai_draft_reply: string | null;
  responded: boolean;
}

export default function GBPPage() {
  const [tab, setTab] = useState<Tab>("posts");
  const [connected, setConnected] = useState<boolean | null>(null);
  const [locationName, setLocationName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Posts state
  const [posts, setPosts] = useState<GBPPost[]>([]);
  const [postsLoading, setPostsLoading] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Reviews state
  const [reviews, setReviews] = useState<GBPReview[]>([]);
  const [reviewStats, setReviewStats] = useState({ total: 0, average: 0, unresponded: 0 });
  const [reviewsLoading, setReviewsLoading] = useState(false);
  const [reviewFilter, setReviewFilter] = useState<"all" | "unresponded" | "low">("all");

  // AI generation state
  const [generatingReply, setGeneratingReply] = useState<string | null>(null);
  const [postingReply, setPostingReply] = useState<string | null>(null);

  useEffect(() => {
    checkConnection();
  }, []);

  async function checkConnection() {
    setLoading(true);
    try {
      const status = await api.get("/api/gbp/oauth/status");
      setConnected(status.connected);
      setLocationName(status.location_name || "");
      if (status.connected) {
        loadPosts();
        loadReviews();
      }
    } catch (e: any) {
      setError(e.message || "Failed to check GBP status");
      setConnected(false);
    } finally {
      setLoading(false);
    }
  }

  async function loadPosts() {
    setPostsLoading(true);
    try {
      const data = await api.get("/api/gbp/posts");
      setPosts(data.posts || []);
    } catch { }
    setPostsLoading(false);
  }

  async function loadReviews() {
    setReviewsLoading(true);
    try {
      const data = await api.get("/api/gbp/reviews");
      setReviews(data.reviews || []);
      setReviewStats({
        total: data.total || data.reviews?.length || 0,
        average: data.average_rating || 0,
        unresponded: data.unresponded_count || 0,
      });
    } catch { }
    setReviewsLoading(false);
  }

  async function handleConnect() {
    try {
      const data = await api.get("/api/gbp/oauth/authorize?origin=settings");
      if (data.auth_url || data.authorization_url) {
        window.location.href = data.auth_url || data.authorization_url;
      }
    } catch (e: any) {
      setError(e.message || "Failed to start GBP connection");
    }
  }

  async function handlePublishPost(postId: string) {
    try {
      await api.post(`/api/gbp/posts/${postId}/publish`);
      loadPosts();
    } catch (e: any) {
      setError(e.message || "Failed to publish post");
    }
  }

  async function handleDeletePost(postId: string) {
    try {
      await api.delete(`/api/gbp/posts/${postId}`);
      setPosts(posts.filter((p) => p.id !== postId));
    } catch (e: any) {
      setError(e.message || "Failed to delete post");
    }
  }

  async function handleGenerateReply(reviewId: string) {
    setGeneratingReply(reviewId);
    try {
      const data = await api.post("/api/gbp/reviews/generate-response", {
        review_id: reviewId,
        tone: "professional",
      });
      if (data.reply) {
        setReviews(reviews.map((r) =>
          r.id === reviewId ? { ...r, ai_draft_reply: data.reply } : r
        ));
      }
    } catch (e: any) {
      setError(e.message || "Failed to generate reply");
    }
    setGeneratingReply(null);
  }

  async function handleApproveReply(reviewId: string) {
    setPostingReply(reviewId);
    try {
      await api.post(`/api/gbp/reviews/${reviewId}/approve-reply`);
      setReviews(reviews.map((r) =>
        r.id === reviewId ? { ...r, responded: true, reply_text: r.ai_draft_reply } : r
      ));
    } catch (e: any) {
      setError(e.message || "Failed to post reply");
    }
    setPostingReply(null);
  }

  const filteredReviews = reviews.filter((r) => {
    if (reviewFilter === "unresponded") return !r.responded;
    if (reviewFilter === "low") return r.rating <= 2;
    return true;
  });

  const postsThisMonth = posts.filter((p) => {
    if (!p.created_at) return false;
    const d = new Date(p.created_at);
    const now = new Date();
    return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
  }).length;

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center min-h-[60vh]">
          <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white">Google Business Profile</h1>
            <p className="text-sm text-white/50 mt-1">
              {connected
                ? `Managing: ${locationName || "Your business"}`
                : "Connect your GBP to manage posts, reviews, and photos"}
            </p>
          </div>
          {connected && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => { loadPosts(); loadReviews(); }}
                className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white/[0.06] text-white/60 hover:text-white hover:bg-white/[0.1] text-sm transition-all"
              >
                <RefreshCw className="w-4 h-4" /> Sync
              </button>
              <button
                onClick={() => setShowCreateModal(true)}
                className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-medium shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30 transition-all"
              >
                <Plus className="w-4 h-4" /> Create Post
              </button>
            </div>
          )}
        </div>

        {/* Error banner */}
        {error && (
          <div className="flex items-center gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            {error}
            <button onClick={() => setError("")} className="ml-auto"><X className="w-4 h-4" /></button>
          </div>
        )}

        {/* Not Connected State */}
        {!connected && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-blue-500/20 to-indigo-500/20 border border-blue-500/30 flex items-center justify-center mb-6">
              <MapPin className="w-10 h-10 text-blue-400" />
            </div>
            <h2 className="text-xl font-bold text-white mb-2">Connect Google Business Profile</h2>
            <p className="text-white/50 max-w-md mb-8">
              Manage your business posts, respond to reviews with AI, and improve your local visibility — all from one place.
            </p>
            <button
              onClick={handleConnect}
              className="px-6 py-3 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-semibold shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30 transition-all"
            >
              <ExternalLink className="w-4 h-4 inline mr-2" />
              Connect Google Business Profile
            </button>
          </div>
        )}

        {/* Connected Content */}
        {connected && (
          <>
            {/* KPI Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="p-5 rounded-2xl bg-white/[0.04] border border-white/[0.06]">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center">
                    <Star className="w-5 h-5 text-amber-400" />
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-white">
                      {reviewStats.average > 0 ? reviewStats.average.toFixed(1) : "—"}
                    </div>
                    <div className="text-xs text-white/40">Average Rating</div>
                  </div>
                </div>
                <div className="text-xs text-white/30">{reviewStats.total} total reviews</div>
              </div>

              <div className="p-5 rounded-2xl bg-white/[0.04] border border-white/[0.06]">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center">
                    <MessageSquare className="w-5 h-5 text-red-400" />
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-white">{reviewStats.unresponded}</div>
                    <div className="text-xs text-white/40">Need Response</div>
                  </div>
                </div>
                <div className="text-xs text-white/30">Reviews awaiting reply</div>
              </div>

              <div className="p-5 rounded-2xl bg-white/[0.04] border border-white/[0.06]">
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center">
                    <FileText className="w-5 h-5 text-emerald-400" />
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-white">{postsThisMonth}</div>
                    <div className="text-xs text-white/40">Posts This Month</div>
                  </div>
                </div>
                <div className="text-xs text-white/30">{posts.length} total posts</div>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex items-center gap-1 p-1 rounded-xl bg-white/[0.04] border border-white/[0.06] w-fit">
              {(["posts", "reviews"] as Tab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                    tab === t
                      ? "bg-white/[0.12] text-white shadow-sm"
                      : "text-white/40 hover:text-white/70"
                  }`}
                >
                  {t === "posts" && <FileText className="w-4 h-4 inline mr-1.5" />}
                  {t === "reviews" && <Star className="w-4 h-4 inline mr-1.5" />}
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>

            {/* Posts Tab */}
            {tab === "posts" && (
              <div className="space-y-3">
                {postsLoading ? (
                  <div className="flex items-center justify-center py-16">
                    <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
                  </div>
                ) : posts.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 text-center">
                    <FileText className="w-12 h-12 text-white/20 mb-4" />
                    <h3 className="text-lg font-semibold text-white mb-1">No posts yet</h3>
                    <p className="text-sm text-white/40 max-w-sm mb-6">
                      GBP posts help customers find you and improve local search rankings.
                    </p>
                    <button
                      onClick={() => setShowCreateModal(true)}
                      className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-medium"
                    >
                      <Plus className="w-4 h-4 inline mr-1.5" /> Create Your First Post
                    </button>
                  </div>
                ) : (
                  posts.map((post) => (
                    <div
                      key={post.id}
                      className="p-5 rounded-2xl bg-white/[0.04] border border-white/[0.06] hover:border-white/[0.1] transition-all"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-2">
                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase ${
                              post.status === "published"
                                ? "bg-emerald-500/15 text-emerald-400"
                                : post.status === "scheduled"
                                ? "bg-amber-500/15 text-amber-400"
                                : "bg-white/10 text-white/50"
                            }`}>
                              {post.status}
                            </span>
                            <span className="text-[10px] text-white/30 uppercase">{post.post_type}</span>
                            {post.auto_generated && (
                              <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-purple-500/15 text-purple-400">
                                AI Generated
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-white/80 leading-relaxed">{post.summary}</p>
                          <div className="flex items-center gap-4 mt-3 text-xs text-white/30">
                            {post.published_at && (
                              <span className="flex items-center gap-1">
                                <Calendar className="w-3 h-3" />
                                {new Date(post.published_at).toLocaleDateString()}
                              </span>
                            )}
                            {post.scheduled_for && post.status === "scheduled" && (
                              <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                Scheduled: {new Date(post.scheduled_for).toLocaleDateString()}
                              </span>
                            )}
                            <span className="flex items-center gap-1">
                              <Eye className="w-3 h-3" /> {post.views || 0}
                            </span>
                            <span className="flex items-center gap-1">
                              <MousePointerClick className="w-3 h-3" /> {post.clicks || 0}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-1">
                          {post.status === "draft" && (
                            <button
                              onClick={() => handlePublishPost(post.id)}
                              className="px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-xs font-medium hover:bg-emerald-500/20 transition-all"
                            >
                              <Send className="w-3 h-3 inline mr-1" /> Publish
                            </button>
                          )}
                          {post.status === "draft" && (
                            <button
                              onClick={() => handleDeletePost(post.id)}
                              className="p-1.5 rounded-lg text-white/20 hover:text-red-400 hover:bg-red-500/10 transition-all"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Reviews Tab */}
            {tab === "reviews" && (
              <div className="space-y-4">
                {/* Filter bar */}
                <div className="flex items-center gap-2">
                  {(["all", "unresponded", "low"] as const).map((f) => (
                    <button
                      key={f}
                      onClick={() => setReviewFilter(f)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                        reviewFilter === f
                          ? "bg-white/[0.12] text-white"
                          : "text-white/40 hover:text-white/70 hover:bg-white/[0.06]"
                      }`}
                    >
                      {f === "all" ? "All Reviews" : f === "unresponded" ? "Need Reply" : "Low Rating"}
                    </button>
                  ))}
                </div>

                {reviewsLoading ? (
                  <div className="flex items-center justify-center py-16">
                    <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
                  </div>
                ) : filteredReviews.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 text-center">
                    <Star className="w-12 h-12 text-white/20 mb-4" />
                    <h3 className="text-lg font-semibold text-white mb-1">
                      {reviewFilter === "all" ? "No reviews yet" : "No matching reviews"}
                    </h3>
                    <p className="text-sm text-white/40 max-w-sm">
                      {reviewFilter === "all"
                        ? "Reviews will appear here once customers leave feedback on Google."
                        : "All reviews in this category have been handled."}
                    </p>
                  </div>
                ) : (
                  filteredReviews.map((review) => (
                    <div
                      key={review.id}
                      className="p-5 rounded-2xl bg-white/[0.04] border border-white/[0.06] hover:border-white/[0.1] transition-all"
                    >
                      <div className="flex items-start justify-between gap-4 mb-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-white">{review.reviewer_name}</span>
                            <div className="flex items-center gap-0.5">
                              {Array.from({ length: 5 }).map((_, i) => (
                                <Star
                                  key={i}
                                  className={`w-3.5 h-3.5 ${
                                    i < review.rating ? "text-amber-400 fill-amber-400" : "text-white/15"
                                  }`}
                                />
                              ))}
                            </div>
                          </div>
                          <div className="text-xs text-white/30 mt-0.5">
                            {review.review_time ? new Date(review.review_time).toLocaleDateString() : ""}
                          </div>
                        </div>
                        {review.responded && (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-emerald-500/15 text-emerald-400">
                            Replied
                          </span>
                        )}
                      </div>

                      {review.comment && (
                        <p className="text-sm text-white/70 leading-relaxed mb-3">{review.comment}</p>
                      )}

                      {/* Reply area */}
                      {review.responded && review.reply_text && (
                        <div className="mt-3 p-3 rounded-xl bg-white/[0.04] border border-white/[0.06]">
                          <div className="text-[10px] uppercase text-white/30 mb-1 font-semibold">Your Reply</div>
                          <p className="text-sm text-white/60">{review.reply_text}</p>
                        </div>
                      )}

                      {/* AI Draft */}
                      {!review.responded && review.ai_draft_reply && (
                        <div className="mt-3 p-3 rounded-xl bg-purple-500/5 border border-purple-500/20">
                          <div className="text-[10px] uppercase text-purple-400 mb-1 font-semibold flex items-center gap-1">
                            <Sparkles className="w-3 h-3" /> AI Draft
                          </div>
                          <p className="text-sm text-white/70 mb-3">{review.ai_draft_reply}</p>
                          <button
                            onClick={() => handleApproveReply(review.id)}
                            disabled={postingReply === review.id}
                            className="px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-xs font-medium hover:bg-emerald-500/20 transition-all disabled:opacity-50"
                          >
                            {postingReply === review.id ? (
                              <Loader2 className="w-3 h-3 inline mr-1 animate-spin" />
                            ) : (
                              <ThumbsUp className="w-3 h-3 inline mr-1" />
                            )}
                            Approve & Post Reply
                          </button>
                        </div>
                      )}

                      {/* Actions */}
                      {!review.responded && !review.ai_draft_reply && (
                        <div className="mt-3 flex items-center gap-2">
                          <button
                            onClick={() => handleGenerateReply(review.id)}
                            disabled={generatingReply === review.id}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500/10 text-purple-400 text-xs font-medium hover:bg-purple-500/20 transition-all disabled:opacity-50"
                          >
                            {generatingReply === review.id ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <Sparkles className="w-3 h-3" />
                            )}
                            Reply with AI
                          </button>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Create Post Modal */}
      {showCreateModal && <CreatePostModal onClose={() => setShowCreateModal(false)} onCreated={loadPosts} />}
    </AppLayout>
  );
}

function CreatePostModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [content, setContent] = useState("");
  const [postType, setPostType] = useState("UPDATE");
  const [cta, setCta] = useState("CALL");
  const [ctaUrl, setCtaUrl] = useState("");
  const [title, setTitle] = useState("");
  const [creating, setCreating] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [aiPrompt, setAiPrompt] = useState("");

  async function handleCreate() {
    if (!content.trim()) { setError("Post content is required"); return; }
    setCreating(true);
    setError("");
    try {
      await api.post("/api/gbp/posts", {
        location_id: "",
        content: content.trim(),
        post_type: postType,
        call_to_action: cta,
        cta_url: ctaUrl || undefined,
        title: title || undefined,
      });
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e.message || "Failed to create post");
    }
    setCreating(false);
  }

  async function handleAiGenerate() {
    if (!aiPrompt.trim()) return;
    setGenerating(true);
    setError("");
    try {
      const data = await api.post("/api/gbp/posts/auto-generate", {
        location_id: "",
        service: aiPrompt.trim(),
        keywords: [],
        headlines: [],
        offers: [],
      });
      if (data.posts && data.posts.length > 0) {
        setContent(data.posts[0].summary);
        setAiPrompt("");
      }
    } catch (e: any) {
      setError(e.message || "AI generation failed");
    }
    setGenerating(false);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative w-full max-w-lg rounded-2xl bg-[#14151a] border border-white/[0.08] shadow-2xl">
        <div className="flex items-center justify-between p-5 border-b border-white/[0.06]">
          <h2 className="text-lg font-bold text-white">Create GBP Post</h2>
          <button onClick={onClose} className="text-white/30 hover:text-white/70">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4 max-h-[70vh] overflow-y-auto">
          {/* AI Generator */}
          <div className="p-4 rounded-xl bg-purple-500/5 border border-purple-500/20">
            <div className="text-xs uppercase text-purple-400 font-semibold mb-2 flex items-center gap-1">
              <Sparkles className="w-3 h-3" /> Generate with AI
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                placeholder="e.g. Spring locksmith special in Dallas"
                className="flex-1 px-3 py-2 rounded-lg bg-white/[0.06] border border-white/[0.08] text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-purple-500/50"
                onKeyDown={(e) => e.key === "Enter" && handleAiGenerate()}
              />
              <button
                onClick={handleAiGenerate}
                disabled={generating || !aiPrompt.trim()}
                className="px-3 py-2 rounded-lg bg-purple-600 text-white text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition-all"
              >
                {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Post Type */}
          <div>
            <label className="text-xs font-medium text-white/50 mb-1.5 block">Post Type</label>
            <div className="flex gap-2">
              {["UPDATE", "OFFER", "EVENT"].map((t) => (
                <button
                  key={t}
                  onClick={() => setPostType(t)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    postType === t
                      ? "bg-white/[0.12] text-white"
                      : "bg-white/[0.04] text-white/40 hover:text-white/70"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          </div>

          {/* Title */}
          <div>
            <label className="text-xs font-medium text-white/50 mb-1.5 block">Title (optional)</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Post headline"
              className="w-full px-3 py-2.5 rounded-xl bg-white/[0.06] border border-white/[0.08] text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-blue-500/50"
            />
          </div>

          {/* Content */}
          <div>
            <label className="text-xs font-medium text-white/50 mb-1.5 block">Content</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={5}
              placeholder="Write your post content..."
              className="w-full px-3 py-2.5 rounded-xl bg-white/[0.06] border border-white/[0.08] text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-blue-500/50 resize-none"
            />
          </div>

          {/* CTA */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-medium text-white/50 mb-1.5 block">Call to Action</label>
              <select
                value={cta}
                onChange={(e) => setCta(e.target.value)}
                className="w-full px-3 py-2.5 rounded-xl bg-white/[0.06] border border-white/[0.08] text-sm text-white focus:outline-none focus:border-blue-500/50"
              >
                <option value="CALL">Call Now</option>
                <option value="LEARN_MORE">Learn More</option>
                <option value="BOOK">Book</option>
                <option value="SIGN_UP">Sign Up</option>
                <option value="ORDER">Order</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-medium text-white/50 mb-1.5 block">CTA URL (optional)</label>
              <input
                type="url"
                value={ctaUrl}
                onChange={(e) => setCtaUrl(e.target.value)}
                placeholder="https://..."
                className="w-full px-3 py-2.5 rounded-xl bg-white/[0.06] border border-white/[0.08] text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-blue-500/50"
              />
            </div>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 p-5 border-t border-white/[0.06]">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-sm text-white/50 hover:text-white hover:bg-white/[0.06] transition-all"
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={creating || !content.trim()}
            className="px-5 py-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 text-white text-sm font-medium disabled:opacity-50 shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30 transition-all"
          >
            {creating ? (
              <><Loader2 className="w-4 h-4 inline mr-1.5 animate-spin" /> Creating...</>
            ) : (
              <><Plus className="w-4 h-4 inline mr-1.5" /> Create Post</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
