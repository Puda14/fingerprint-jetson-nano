import { useEffect, useRef } from 'react';

interface FingerprintCanvasProps {
  imageData: string | null; // base64 encoded grayscale image
  width?: number;
  height?: number;
  qualityScore?: number | null;
  showQuality?: boolean;
  className?: string;
}

function FingerprintCanvas({
  imageData,
  width = 192,
  height = 192,
  qualityScore = null,
  showQuality = true,
  className = '',
}: FingerprintCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    if (!imageData) {
      // Draw placeholder
      ctx.fillStyle = '#1B4F72';
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = '#ffffff40';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('No Image', width / 2, height / 2);
      return;
    }

    const img = new Image();
    img.onload = () => {
      ctx.clearRect(0, 0, width, height);
      ctx.drawImage(img, 0, 0, width, height);
    };
    img.onerror = () => {
      ctx.fillStyle = '#E74C3C';
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = '#ffffff';
      ctx.font = '12px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('Load Error', width / 2, height / 2);
    };

    // Handle both raw base64 and data URI formats
    if (imageData.startsWith('data:')) {
      img.src = imageData;
    } else {
      img.src = `data:image/png;base64,${imageData}`;
    }
  }, [imageData, width, height]);

  const getQualityColor = (score: number): string => {
    if (score >= 80) return 'text-success';
    if (score >= 60) return 'text-warning';
    return 'text-danger';
  };

  const getQualityLabel = (score: number): string => {
    if (score >= 80) return 'Good';
    if (score >= 60) return 'Fair';
    return 'Poor';
  };

  return (
    <div className={`inline-flex flex-col items-center gap-2 ${className}`}>
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        className="rounded-lg border-2 border-gray-200 bg-gray-900"
        style={{ imageRendering: 'pixelated' }}
      />
      {showQuality && qualityScore !== null && (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-dark-lighter">Quality:</span>
          <span className={`font-semibold ${getQualityColor(qualityScore)}`}>
            {qualityScore}% ({getQualityLabel(qualityScore)})
          </span>
        </div>
      )}
    </div>
  );
}

export default FingerprintCanvas;
