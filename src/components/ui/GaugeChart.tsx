import { cn } from "@/lib/utils";

interface GaugeChartProps {
  value: number;
  max?: number;
  label: string;
  sublabel?: string;
  colorClass?: string;
  size?: "sm" | "md" | "lg";
}

export function GaugeChart({ 
  value, 
  max = 100, 
  label, 
  sublabel,
  colorClass = "text-primary",
  size = "md" 
}: GaugeChartProps) {
  const percentage = Math.min((value / max) * 100, 100);
  const rotation = (percentage / 100) * 180;
  
  const sizeClasses = {
    sm: "w-24 h-12",
    md: "w-32 h-16",
    lg: "w-40 h-20"
  };
  
  const textSizes = {
    sm: "text-lg",
    md: "text-2xl",
    lg: "text-3xl"
  };

  return (
    <div className="flex flex-col items-center">
      <div className={cn("relative", sizeClasses[size])}>
        {/* Background arc */}
        <div className="absolute inset-0 overflow-hidden">
          <div 
            className="absolute bottom-0 left-0 right-0 h-full rounded-t-full border-8 border-muted"
            style={{ borderBottom: 'none' }}
          />
        </div>
        
        {/* Colored arc */}
        <div className="absolute inset-0 overflow-hidden">
          <div 
            className={cn("absolute bottom-0 left-0 right-0 h-full rounded-t-full border-8 border-transparent", colorClass)}
            style={{ 
              borderBottom: 'none',
              clipPath: `polygon(0 100%, 50% 50%, ${50 + 50 * Math.cos((180 - rotation) * Math.PI / 180)}% ${50 - 50 * Math.sin((180 - rotation) * Math.PI / 180)}%, 50% 100%)`,
              borderColor: 'currentColor'
            }}
          />
        </div>
        
        {/* Center value */}
        <div className="absolute bottom-0 left-0 right-0 flex flex-col items-center">
          <span className={cn("font-semibold", textSizes[size])}>{value}</span>
        </div>
      </div>
      
      <div className="mt-2 text-center">
        <p className="text-sm font-medium">{label}</p>
        {sublabel && <p className="text-xs text-muted-foreground">{sublabel}</p>}
      </div>
    </div>
  );
}
