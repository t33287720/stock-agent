import Portfolio from "../components/Portfolio";

export default function PortfolioPage() {
  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold mb-4">我的持股組合</h1>
      <Portfolio />
    </div>
  );
}