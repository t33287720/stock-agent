export default function NewsList({ news }) {
  return (
    <div className="mt-4">
      <h2 className="text-xl font-bold mb-2">重大訊息</h2>
      <ul className="list-disc pl-5">
        {news.map((n, idx) => (
          <li key={idx} className="mb-1">
            {n.title} ({n.date})
          </li>
        ))}
      </ul>
    </div>
  );
}