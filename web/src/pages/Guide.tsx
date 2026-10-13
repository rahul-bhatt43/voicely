import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { PageHeader } from "../components/ui";

const TOC = [
  ["how", "How it works"],
  ["record", "Recording a voice"],
  ["train", "Training here"],
  ["colab", "Training on Colab"],
  ["import", "Importing a model"],
  ["results", "Getting good results"],
  ["rules", "Permission and labelling"],
];

function Part({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24">
      <h2 className="text-2xl font-bold mb-3">{title}</h2>
      <div className="space-y-3 text-[15px] leading-relaxed [&_li]:ml-5 [&_ol]:list-decimal [&_ul]:list-disc [&_ol]:space-y-1.5 [&_ul]:space-y-1.5 [&_strong]:text-text [&_strong]:font-semibold text-text/85">
        {children}
      </div>
    </section>
  );
}

const Code = ({ children }: { children: ReactNode }) => (
  <code className="font-mono text-[13px] bg-raised border border-line rounded px-1.5 py-0.5">{children}</code>
);

export default function Guide() {
  return (
    <>
      <PageHeader eyebrow="Guide" title="Build a custom voice, start to finish">
        What a voice model is, how to record for one, and how to train it here or on a free GPU.
      </PageHeader>

      <div className="grid gap-10 lg:grid-cols-[13rem_1fr]">
        <nav className="hidden lg:block sticky top-24 self-start text-sm space-y-1">
          {TOC.map(([id, label]) => (
            <a key={id} href={`#${id}`} className="block rounded-lg px-3 py-1.5 text-muted hover:text-text hover:bg-raised">{label}</a>
          ))}
        </nav>

        <div className="space-y-12 max-w-3xl">
          <Part id="how" title="How it works">
            <p>
              Voicely changes <strong>who</strong> is performing, not <strong>what</strong> is performed. You give it a
              performance (a song, a spoken clip, or text read by a narrator) and a voice model. It keeps the words,
              timing and melody and re-renders them in the model's voice.
            </p>
            <p>
              A voice model is one small file (<Code>.pth</Code>, about 55 MB) and usually an index file
              (<Code>.index</Code>) that helps the result sound more like the speaker. Swapping voices means swapping
              those files.
            </p>
            <p>
              Because the performance comes from the source, so do the accent, pacing and pronunciation. A voice model
              gives someone's <em>sound</em> to another person's delivery. It won't make them perform like the target.
            </p>
          </Part>

          <Part id="record" title="Recording a voice">
            <p>The recordings decide the quality of the voice more than any setting does. Aim for:</p>
            <ul>
              <li><strong>10 to 30 minutes</strong> of one person. Two minutes is the minimum to train at all; ten is where it starts to convince.</li>
              <li><strong>Dry and clean.</strong> A quiet, soft-furnished room. No music, no echo, no fan or traffic. Anything in the background gets learned as part of the voice.</li>
              <li><strong>No clipping.</strong> Stay a hand's width from the mic and keep the loudest moments below the top of the meter.</li>
              <li><strong>Variety.</strong> Quiet and loud, low and high, statements and questions. If the voice will sing, include singing across its range.</li>
              <li><strong>One consistent setup.</strong> Same mic, same room, same distance. Mixed sources make a model that sounds like none of them.</li>
              <li><strong>Lossless if you can.</strong> WAV or FLAC. A phone voice memo in a quiet room still beats a studio take with music under it.</li>
            </ul>
            <p>
              Each recording you add is measured for clipping, background noise and silence, and flagged if something's
              wrong. Long silences are fine; they're cut out automatically before training.
            </p>
            <p>
              Only have recordings with music behind them? Separate the vocals in a stem-splitting tool first and
              upload only the vocal. Separated vocals are usable, but never as good as a dry recording.
            </p>
          </Part>

          <Part id="train" title="Training here">
            <ol>
              <li>Go to <Link to="/voices/new" className="text-accent hover:underline">Voices → New voice</Link>, name it and confirm permission.</li>
              <li>Add recordings until the meter says you have enough.</li>
              <li>Pick the number of training passes and press <strong>Start training</strong>.</li>
              <li>When it finishes, the voice is marked Ready and shows up when you create something.</li>
            </ol>
            <p>Training runs five stages: slicing the audio into short clips, extracting pitch, extracting voice features, fine-tuning the model, and building the index.</p>
            <p>
              <strong>Training needs a GPU to be practical.</strong> The top bar shows whether this server has one. On a
              CPU-only server training still runs, which is useful for a short trial to confirm your recordings work, but
              a finished voice would take far too long. In that case use Colab, below.
            </p>
            <p>
              <strong>How many passes?</strong> For 10 to 30 minutes of audio, 200 to 300 is a sensible range. If the
              result sounds robotic or metallic, the usual cause is the recordings, not too few passes.
            </p>
          </Part>

          <Part id="colab" title="Training on Colab">
            <p>
              Google Colab lends you an NVIDIA GPU for free. Voicely ships a notebook that runs the same training
              pipeline as the server, so the result imports back as one file. You need a Google account.
            </p>
            <ol>
              <li>On the voice's page, under <strong>2. Train</strong>, download <strong>Recordings (.zip)</strong> and <strong>Notebook (.ipynb)</strong>.</li>
              <li>Open <a className="text-accent hover:underline" href="https://colab.research.google.com/" target="_blank" rel="noreferrer">colab.research.google.com</a>, choose <strong>File → Upload notebook</strong>, and pick the notebook.</li>
              <li>Choose <strong>Runtime → Change runtime type → T4 GPU</strong> and save.</li>
              <li>In step 1 of the notebook, set a name and the number of epochs (200 is a good start), then choose <strong>Runtime → Run all</strong>.</li>
              <li>Installing takes a few minutes. Step 3 then shows a <strong>Choose files</strong> button: pick the recordings zip.</li>
              <li>Training prints a line as each epoch starts. When it ends, your browser downloads a file ending in <Code>-voicely.zip</Code>.</li>
              <li>Back here, open the voice, choose <strong>Import a trained model</strong> and upload that zip. It holds both the model and its index.</li>
            </ol>
            <p><strong>If something goes wrong:</strong></p>
            <ul>
              <li><strong>"NO GPU" in step 1.</strong> The runtime type wasn't changed, or Colab has no free GPU right now. Set T4 GPU and run again, or try later.</li>
              <li><strong>The session disconnected.</strong> Free Colab stops when the tab is idle or after a few hours. Keep the tab open, and for long datasets use fewer epochs. A disconnected run can't be resumed, so run all again.</li>
              <li><strong>Out of memory.</strong> Lower the batch size in step 1 to 4 and run again.</li>
              <li><strong>The download didn't start.</strong> Open the folder icon in Colab's left bar and download the <Code>-voicely.zip</Code> file from there.</li>
            </ul>
            <p>
              Your recordings go to your own Colab session, which Google deletes when the session ends. Nothing comes
              back to Voicely until you import the zip yourself.
            </p>
            <p>
              Prefer another trainer? Applio and the RVC-Project WebUI also work: choose v2, 40k and RMVPE, train the
              index too, then import <Code>weights/NAME.pth</Code> with <Code>logs/NAME/added_*.index</Code>.
            </p>
          </Part>

          <Part id="import" title="Importing a model">
            <ul>
              <li>Upload the <strong>small</strong> <Code>.pth</Code> from the <Code>weights</Code> folder. Files named <Code>G_*.pth</Code> or <Code>D_*.pth</Code> are training checkpoints: they're several hundred MB and can't be used as a voice.</li>
              <li>The index to use starts with <Code>added_</Code>. A file starting with <Code>trained_</Code> is an intermediate and won't work.</li>
              <li>The index is optional. Without it the voice still works; with it the result leans closer to the speaker.</li>
              <li>Both RVC v1 and v2 models load. The file records which it is.</li>
            </ul>
          </Part>

          <Part id="results" title="Getting good results">
            <ul>
              <li><strong>Set the pitch first.</strong> If a low source voice drives a high target voice (or the reverse), shift by a full octave: +12 or −12. For songs, an octave keeps the vocal in key; smaller shifts need the Song key control so the music moves too.</li>
              <li><strong>Start from a clean source.</strong> For a song with music, always use Song cover so the vocals are separated first. Feeding a full mix into Voice swap garbles it.</li>
              <li><strong>Hearing the original singer bleed through?</strong> Raise Voice character.</li>
              <li><strong>Hearing metallic or watery artifacts?</strong> Lower Voice character, and check the source for reverb.</li>
              <li><strong>Consonants or breaths sound smeared?</strong> Lower Consonant protection to protect them more.</li>
              <li><strong>Harmonies and stacked backing vocals</strong> convert less cleanly than a single lead line; the pitch tracker follows one note at a time.</li>
              <li><strong>Text to voice</strong> sounds most natural when the narrator's pitch is already near the target voice's, so little or no pitch shift is needed.</li>
            </ul>
          </Part>

          <Part id="rules" title="Permission and labelling">
            <ul>
              <li>Clone only your own voice, or a voice whose owner has clearly agreed. That confirmation is saved with every voice, and you can add a spoken statement to it.</li>
              <li>Voice models of celebrities and other real people found online were almost always made without permission. Don't import them.</li>
              <li>Sharing a voice with everyone on the server needs the owner's agreement to that as well, not just to cloning.</li>
              <li>Every file Voicely produces carries an "AI-generated" note in its metadata. Don't strip it, and say so when you publish.</li>
              <li>Using a voice to impersonate someone, to deceive, or to put words in a real person's mouth is misuse. Shared voices can be reported from their page.</li>
              <li>Cover songs involve the songwriter's and label's rights too. A cover for yourself is one thing; publishing one is another.</li>
            </ul>
          </Part>
        </div>
      </div>
    </>
  );
}
