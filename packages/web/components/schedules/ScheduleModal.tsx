"use client";

import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { schedules } from "@/lib/api";

type ScheduleModalProps = {
  isOpen: boolean;
  onClose: () => void;
  projectSlug: string;
  pipelineSlug?: string;
  existingSchedule?: any; // You can type this properly later based on the API response
  onSuccess: () => void;
  pipelines?: { slug: string; name: string }[]; // Passed in when pipelineSlug is not provided
};

const FREQUENCIES = [
  { value: "Hourly", label: "Hourly", cron: "0 * * * *" },
  { value: "Daily", label: "Daily", cron: "0 0 * * *" },
  { value: "Weekly", label: "Weekly", cron: "0 0 * * 0" },
  { value: "Custom", label: "Custom cron", cron: "" },
];

export function ScheduleModal({
  isOpen,
  onClose,
  projectSlug,
  pipelineSlug,
  existingSchedule,
  onSuccess,
  pipelines
}: ScheduleModalProps) {
  const [selectedPipelineSlug, setSelectedPipelineSlug] = useState<string>(pipelineSlug || "");
  const [frequency, setFrequency] = useState("Daily");
  const [customCron, setCustomCron] = useState("");
  const [window, setWindow] = useState("None");
  const [customWindow, setCustomWindow] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (existingSchedule) {
      setFrequency(existingSchedule.frequency || "Daily");
      setCustomCron(existingSchedule.cron || "");
      if (existingSchedule.windowEndsAt) {
        // Compute window somehow from windowEndsAt?
        // For simplicity, let's say "Custom" if it's set
        setWindow("Custom");
      } else {
        setWindow("None");
      }
      setEnabled(existingSchedule.enabled ?? true);
      setSelectedPipelineSlug(existingSchedule.pipelineSlug);
    } else {
      setSelectedPipelineSlug(pipelineSlug || (pipelines && pipelines.length > 0 ? pipelines[0].slug : ""));
      setFrequency("Daily");
      setCustomCron("");
      setWindow("None");
      setCustomWindow("");
      setEnabled(true);
    }
  }, [existingSchedule, pipelineSlug, pipelines, isOpen]);

  const handleSubmit = async () => {
    setLoading(true);
    try {
      let cronToUse = FREQUENCIES.find(f => f.value === frequency)?.cron;
      if (frequency === "Custom") cronToUse = customCron;

      let windowEndsAt: number | undefined = undefined;
      const now = Date.now();
      if (window === "7 days") windowEndsAt = now + 7 * 24 * 60 * 60 * 1000;
      else if (window === "14 days") windowEndsAt = now + 14 * 24 * 60 * 60 * 1000;
      else if (window === "30 days") windowEndsAt = now + 30 * 24 * 60 * 60 * 1000;
      else if (window === "Custom" && customWindow) windowEndsAt = now + parseInt(customWindow) * 24 * 60 * 60 * 1000;

      const payload = {
        project_slug: projectSlug,
        pipeline_slug: selectedPipelineSlug,
        frequency,
        cron: cronToUse,
        window: window,
        window_ends_at: windowEndsAt,
        enabled,
      };

      if (existingSchedule) {
        await schedules.update(existingSchedule._id, payload);
      } else {
        await schedules.create(payload);
        alert("Schedule created successfully"); // fallback toast, we could use toast library here
      }

      onSuccess();
      onClose();
    } catch (e) {
      console.error(e);
      alert("Failed to save schedule.");
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async () => {
    if (!existingSchedule) return;
    setLoading(true);
    try {
      await schedules.remove(existingSchedule._id);
      onSuccess();
      onClose();
    } catch (e) {
      console.error(e);
      alert("Failed to remove schedule.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{existingSchedule ? "Edit Schedule" : "Create Schedule"}</DialogTitle>
          <DialogDescription>
            Configure automatic execution for this pipeline.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          {!pipelineSlug && pipelines && (
             <div className="grid gap-2">
                <Label htmlFor="pipeline">Pipeline</Label>
                <Select value={selectedPipelineSlug} onValueChange={setSelectedPipelineSlug}>
                  <SelectTrigger id="pipeline">
                    <SelectValue placeholder="Select pipeline" />
                  </SelectTrigger>
                  <SelectContent>
                    {pipelines.map(p => (
                      <SelectItem key={p.slug} value={p.slug}>{p.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
             </div>
          )}
          <div className="grid gap-2">
            <Label>Frequency</Label>
            <RadioGroup value={frequency} onValueChange={setFrequency} className="flex gap-4">
              {FREQUENCIES.map(f => (
                <div key={f.value} className="flex items-center space-x-2">
                  <RadioGroupItem value={f.value} id={`r-${f.value}`} />
                  <Label htmlFor={`r-${f.value}`}>{f.label}</Label>
                </div>
              ))}
            </RadioGroup>
          </div>

          {frequency === "Custom" && (
            <div className="grid gap-2">
              <Label htmlFor="cron">Cron Expression</Label>
              <Input
                id="cron"
                placeholder="0 0 * * *"
                value={customCron}
                onChange={(e) => setCustomCron(e.target.value)}
              />
            </div>
          )}

          <div className="grid gap-2">
            <Label htmlFor="window">Collection Window</Label>
            <Select value={window} onValueChange={setWindow}>
              <SelectTrigger id="window">
                <SelectValue placeholder="Select window" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="None">None (Indefinite)</SelectItem>
                <SelectItem value="7 days">7 days</SelectItem>
                <SelectItem value="14 days">14 days</SelectItem>
                <SelectItem value="30 days">30 days</SelectItem>
                <SelectItem value="Custom">Custom days</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {window === "Custom" && (
            <div className="grid gap-2">
              <Label htmlFor="customWindow">Days</Label>
              <Input
                id="customWindow"
                type="number"
                min="1"
                placeholder="Number of days"
                value={customWindow}
                onChange={(e) => setCustomWindow(e.target.value)}
              />
            </div>
          )}

          <div className="flex items-center space-x-2">
            <Checkbox
              id="enabled"
              checked={enabled}
              onCheckedChange={(checked) => setEnabled(checked === true)}
            />
            <Label htmlFor="enabled">Enable immediately</Label>
          </div>
        </div>
        <DialogFooter className="flex justify-between w-full">
          {existingSchedule ? (
            <Button variant="destructive" onClick={handleRemove} disabled={loading}>
              Remove
            </Button>
          ) : <div />}
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose} disabled={loading}>
              Cancel
            </Button>
            <Button onClick={handleSubmit} disabled={loading || (frequency === "Custom" && !customCron) || (window === "Custom" && !customWindow) || !selectedPipelineSlug}>
              {loading ? "Saving..." : "Save"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}