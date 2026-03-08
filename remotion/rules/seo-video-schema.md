# SEO: VideoObject Schema

When creating videos with Remotion, also create VideoObject JSON-LD schema for SEO. This tells search engines about your video so it can appear in Google Video search and get rich results (thumbnails in search).

## What VideoObject Schema Does

The schema is metadata *about* the video, not the video itself. The video stays mp4 - you add a JSON-LD script tag describing it:

```json
{
  "@context": "https://schema.org",
  "@type": "VideoObject",
  "name": "How Our Product Works",
  "description": "A 2-minute explainer showing...",
  "thumbnailUrl": "https://cdn.example.com/video-thumb.jpg",
  "contentUrl": "https://cdn.example.com/video.mp4",
  "duration": "PT2M30S",
  "uploadDate": "2025-01-15"
}
```

## Required Fields

| Field | Description | Example |
|-------|-------------|---------|
| `name` | Video title | "How HTMA Testing Works" |
| `description` | What the video shows | "See how our program..." |
| `thumbnailUrl` | Preview image URL | Must be actual image, not video frame |
| `uploadDate` | ISO 8601 date | "2025-01-15" |

## Recommended Fields

| Field | Description | Example |
|-------|-------------|---------|
| `duration` | ISO 8601 duration | "PT2M30S" (2 min 30 sec) |
| `contentUrl` | Direct video URL | mp4/webm URL |
| `embedUrl` | Embeddable player URL | YouTube embed URL |

## Duration Format (ISO 8601)

```
PT1H30M45S = 1 hour, 30 minutes, 45 seconds
PT5M = 5 minutes
PT2M30S = 2 minutes, 30 seconds
PT45S = 45 seconds
```

## Thumbnail Best Practices

- **Create a custom thumbnail** - Don't just use a video frame
- **Minimum 1280x720** for HD display in search results
- **Export from Remotion** using `<Still>` composition:

```tsx
// In your Remotion project
export const VideoThumbnail: React.FC = () => (
  <AbsoluteFill style={{ background: '#1a1a2e' }}>
    <h1>Your Video Title</h1>
    <PlayButton /> {/* Visual indicator it's a video */}
  </AbsoluteFill>
);

// Register as Still
<Still
  id="video-thumbnail"
  component={VideoThumbnail}
  width={1280}
  height={720}
/>
```

Render with: `npx remotion still video-thumbnail out/thumbnail.jpg`

## Implementation Pattern

Create a reusable schema builder:

```typescript
// src/seo/videoSchema.ts
export type VideoSchemaOptions = {
  name: string;
  description: string;
  thumbnailUrl: string;
  duration: string; // ISO 8601: PT2M30S
  uploadDate: string; // ISO 8601: 2025-01-15
  contentUrl?: string;
  embedUrl?: string;
};

export function buildVideoSchema(options: VideoSchemaOptions): object {
  return {
    "@context": "https://schema.org",
    "@type": "VideoObject",
    name: options.name,
    description: options.description,
    thumbnailUrl: options.thumbnailUrl,
    uploadDate: options.uploadDate,
    duration: options.duration,
    ...(options.contentUrl && { contentUrl: options.contentUrl }),
    ...(options.embedUrl && { embedUrl: options.embedUrl }),
  };
}
```

## Checklist for Each Video

When publishing a Remotion video:

1. [ ] Export thumbnail as Still (1280x720 minimum)
2. [ ] Upload video to CDN/hosting
3. [ ] Upload thumbnail to same CDN
4. [ ] Note the exact duration (from Remotion: `durationInFrames / fps`)
5. [ ] Add VideoObject schema to the page where video appears
6. [ ] Test with [Google Rich Results Test](https://search.google.com/test/rich-results)

## When to Skip

VideoObject schema is **lower priority** for:
- Internal/private videos
- Videos that don't need search visibility
- Landing pages where Service/FAQ schemas matter more

Focus on VideoObject when:
- Video is a key piece of content
- You want the video indexed in Google Video search
- You want video thumbnails in regular search results
