function classForLine(line: string) {
  if (line.startsWith("+")) return "diff-add";
  if (line.startsWith("-")) return "diff-del";
  if (line.startsWith("@") || line.startsWith("diff")) return "diff-meta";
  return "";
}

export function DiffBlock({ diff }: { diff: string }) {
  return (
    <pre className="code">
      {diff.split("\n").map((line, index) => (
        <span className={`diff-line ${classForLine(line)}`} key={`${index}-${line}`}>
          {line}
        </span>
      ))}
    </pre>
  );
}
