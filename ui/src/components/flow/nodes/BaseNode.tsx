import { forwardRef, HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const BaseNode = forwardRef<
    HTMLDivElement,
    HTMLAttributes<HTMLDivElement> & {
        selected?: boolean;
        invalid?: boolean;
    }
>(({ className, selected, invalid, ...props }, ref) => (
    <div
        ref={ref}
        className={cn(
            "relative rounded-md border bg-card p-5 text-card-foreground min-w-[300px] min-h-[100px]",
            className,
            selected ? "border-muted-foreground shadow-lg" : "",
            invalid ? "border-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]" : "",
            "hover:ring-1",
        )}
        tabIndex={0}
        {...props}
    />
));

BaseNode.displayName = "BaseNode";
